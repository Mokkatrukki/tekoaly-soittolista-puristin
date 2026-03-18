"""
Wikipedia & Wikidata -wrapperit.

Kaksi erillistä tietolähdettä:

Wikipedia Action API — artikkelit wikitextinä
  get_article(title)           → raaka wikitext
  get_section(title, section)  → tietty osio tekstinä
  get_infobox(title)           → infobox dict:ksi parsittuna
  get_tracklist(movie_title)   → soundtrack-tracklist [{title, artist, length}]
  search(query, limit)         → artikkelien haku

Wikidata SPARQL — strukturoitu tieto kyselykielellä
  sparql(query)                          → raaka SPARQL-tulos
  oscar_winners(category, year_from)     → Oscar-voittajat [{year, film, film_id}]
  artists_by_genre(genre, country)       → artistit genren/maan mukaan
  film_soundtrack_album(film_title)      → elokuvan soundtrack-albumin Wikidata-ID

Ei API-avaimia tarvita. Rate limit: Wikipedia ~200 req/s, Wikidata SPARQL on reilu.
"""

import re
import time
import urllib.parse
import urllib.request
import json
from dataclasses import dataclass


USER_AGENT = "SoittolistaPuristin/0.1 mokkatrukki@gmail.com"

# Wikidata entity ID:t Oscar-kategorioille + kohteen tyyppi (film/person)
# (type = Wikidata instance-of ID jolla suodatetaan turhat rivit pois)
OSCAR_CATEGORIES = {
    "best_picture":        ("Q102427",  "Q11424"),   # film
    "best_original_score": ("Q488651",  None),        # person (säveltäjä)
    "best_original_song":  ("Q112243",  None),        # person/work
    "best_director":       ("Q103360",  None),        # person
    "best_actor":          ("Q103618",  None),        # person
    "best_actress":        ("Q105989",  None),        # person
}


# ─── Dataluokat ──────────────────────────────────────────────────────────────

@dataclass
class TrackEntry:
    position: int
    title: str
    artist: str
    length: str      # "3:42" tai ""

    def __str__(self) -> str:
        parts = [f"{self.position}.", self.title]
        if self.artist:
            parts.append(f"— {self.artist}")
        if self.length:
            parts.append(f"[{self.length}]")
        return " ".join(parts)


# ─── HTTP-apufunktiot ────────────────────────────────────────────────────────

def _get(url: str, params: dict | None = None, timeout: int = 15) -> dict | str:
    """Tee GET-pyyntö, palauta JSON-dict tai teksti."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        ct = r.headers.get("content-type", "")
        if "json" in ct:
            return json.loads(raw)
        return raw.decode("utf-8")


# ─── Wikipedia API ───────────────────────────────────────────────────────────

def get_article(title: str) -> str:
    """
    Hae Wikipedia-artikkelin raaka wikitext.
    title: artikkelin nimi, esim. "Seven_(soundtrack)" tai "Blade Runner"
    """
    data = _get("https://en.wikipedia.org/w/api.php", {
        "action": "query",
        "titles": title,
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "format": "json",
        "formatversion": "2",
    })
    pages = data["query"]["pages"]
    if not pages or "missing" in pages[0]:
        return ""
    return pages[0]["revisions"][0]["slots"]["main"]["content"]


def get_section(title: str, section_keyword: str) -> str:
    """
    Hae tietty osio Wikipedia-artikkelista.
    section_keyword: osion otsikossa esiintyvä sana, esim. "track listing", "personnel"
    Palauttaa osion tekstinä (wikitext).
    """
    wikitext = get_article(title)
    if not wikitext:
        return ""

    lines = wikitext.split("\n")
    in_section = False
    result = []
    keyword_lower = section_keyword.lower()

    for line in lines:
        # Osion alkaminen: == Otsikko ==
        if re.match(r"^==+\s*.+\s*==+$", line):
            if keyword_lower in line.lower():
                in_section = True
                continue
            elif in_section:
                break  # seuraava osio alkoi
        if in_section:
            result.append(line)

    return "\n".join(result)


def get_infobox(title: str) -> dict:
    """
    Parsii artikkelin infoboxin key-value -dictiksi.
    Toimii useimmille elokuva/albumi/artisti-infoboxeille.
    """
    wikitext = get_article(title)
    if not wikitext:
        return {}

    # Etsi infobox-blokki
    match = re.search(r"\{\{[Ii]nfobox[^}]*?\n(.*?)^\}\}", wikitext, re.DOTALL | re.MULTILINE)
    if not match:
        # Yritä löytää mikä tahansa {{ ... }} jossa on | = rakenne
        match = re.search(r"\{\{[A-Z][^\n]*\n(.*?)^\}\}", wikitext, re.DOTALL | re.MULTILINE)
    if not match:
        return {}

    result = {}
    for line in match.group(1).split("\n"):
        m = re.match(r"\s*\|\s*(\w+)\s*=\s*(.+)", line)
        if m:
            key = m.group(1).strip()
            value = _clean_wikitext(m.group(2).strip())
            result[key] = value
    return result


def get_tracklist(movie_title: str) -> list[TrackEntry]:
    """
    Hae elokuvan soundtrack-tracklist Wikipediasta.

    Etsii artikkelin "[movie_title] (soundtrack)" tai "[movie_title] (film score)".
    Parsii {{Track listing}} -templaten.

    Palauttaa: [TrackEntry(position, title, artist, length)]
    """
    # Kokeile eri artikkelinimiä
    candidates = [
        f"{movie_title} (soundtrack)",
        f"{movie_title} (film score)",
        f"{movie_title} (score)",
        movie_title,
    ]

    wikitext = ""
    for candidate in candidates:
        wikitext = get_article(candidate)
        if wikitext:
            break

    if not wikitext:
        return []

    return _parse_track_listing(wikitext)


def search(query: str, limit: int = 5) -> list[dict]:
    """
    Hae Wikipedia-artikkeleita hakusanalla.
    Palauttaa: [{title, snippet, pageid}]
    """
    data = _get("https://en.wikipedia.org/w/api.php", {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": limit,
        "format": "json",
    })
    results = []
    for r in data.get("query", {}).get("search", []):
        results.append({
            "title": r.get("title", ""),
            "snippet": _clean_wikitext(r.get("snippet", "")),
            "pageid": r.get("pageid"),
        })
    return results


# ─── Wikidata SPARQL ─────────────────────────────────────────────────────────

def sparql(query: str) -> list[dict]:
    """
    Suorita Wikidata SPARQL -kysely.
    Palauttaa rows listana [{var: value, ...}].
    """
    data = _get("https://query.wikidata.org/sparql", {
        "query": query,
        "format": "json",
    })
    rows = []
    for binding in data.get("results", {}).get("bindings", []):
        row = {}
        for key, val in binding.items():
            row[key] = val.get("value", "")
        rows.append(row)
    return rows


def oscar_winners(
    category: str = "best_picture",
    year_from: int = 2000,
    year_to: int = 2026,
) -> list[dict]:
    """
    Hae Oscar-voittajat Wikidatasta.

    category: "best_picture" | "best_original_score" | "best_original_song" |
              "best_director" | "best_actor" | "best_actress"
    Palauttaa: [{year, title, wikidata_id}] deduploituna, järjestyksessä uusin ensin.
    """
    cat = OSCAR_CATEGORIES.get(category)
    if not cat:
        raise ValueError(f"Tuntematon kategoria: {category}. Valinnat: {list(OSCAR_CATEGORIES)}")
    award_id, instance_type = cat

    type_filter = f"?item wdt:P31 wd:{instance_type} ." if instance_type else ""

    query = f"""
SELECT DISTINCT ?item ?itemLabel ?ceremonyYear WHERE {{
  {type_filter}
  ?item p:P166 ?awardStmt .
  ?awardStmt ps:P166 wd:{award_id} .
  ?awardStmt pq:P585 ?date .
  BIND(YEAR(?date) AS ?ceremonyYear)
  FILTER(?ceremonyYear >= {year_from} && ?ceremonyYear <= {year_to})
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" }}
}}
ORDER BY DESC(?ceremonyYear)
"""
    rows = sparql(query)

    # Deduploi: yksi voittaja per vuosi (voi tulla duplikaatteja eri awardStatement-syistä)
    seen: set[tuple] = set()
    results = []
    for row in rows:
        year = row.get("ceremonyYear", "")
        title = row.get("itemLabel", "")
        wid = row.get("item", "").split("/")[-1]  # Q-numero URLista
        key = (year, title)
        if key not in seen:
            seen.add(key)
            results.append({"year": year, "title": title, "wikidata_id": wid})

    return results


def artists_by_genre(genre: str, country: str = "", limit: int = 20) -> list[dict]:
    """
    Hae artisteja Wikidatasta genren ja optionaalisesti maan mukaan.
    genre: genre-string, esim. "jazz", "city pop", "ambient"
    country: maa englanniksi, esim. "Japan", "Finland"
    Palauttaa: [{name, wikidata_id, country, genre}]

    Huom: Wikidata-genrehaku on epätäydellinen — käytä Last.fm:ää tarkempaan discoveryyn.
    """
    country_filter = ""
    if country:
        country_filter = f'?item wdt:P27 ?country . ?country rdfs:label "{country}"@en .'

    query = f"""
SELECT DISTINCT ?item ?itemLabel ?countryLabel WHERE {{
  ?item wdt:P31 wd:Q5 .  # ihminen
  ?item wdt:P136 ?genre .
  ?genre rdfs:label "{genre}"@en .
  {country_filter}
  OPTIONAL {{ ?item wdt:P27 ?country }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" }}
}}
LIMIT {limit}
"""
    rows = sparql(query)
    results = []
    for row in rows:
        results.append({
            "name": row.get("itemLabel", ""),
            "wikidata_id": row.get("item", "").split("/")[-1],
            "country": row.get("countryLabel", ""),
        })
    return results


def film_info(film_title: str) -> dict:
    """
    Hae elokuvan perustiedot Wikidatasta: vuosi, ohjaaja, genre, soundtrack-artisti.
    Palauttaa: {title, year, director, genres, composer, wikidata_id}
    """
    query = f"""
SELECT DISTINCT ?item ?itemLabel ?year ?directorLabel ?composerLabel ?genreLabel WHERE {{
  ?item wdt:P31 wd:Q11424 .  # elokuva
  ?item rdfs:label "{film_title}"@en .
  OPTIONAL {{ ?item wdt:P577 ?releaseDate . BIND(YEAR(?releaseDate) AS ?year) }}
  OPTIONAL {{ ?item wdt:P57 ?director }}
  OPTIONAL {{ ?item wdt:P86 ?composer }}
  OPTIONAL {{ ?item wdt:P136 ?genre }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" }}
}}
LIMIT 10
"""
    rows = sparql(query)
    if not rows:
        return {}

    # Kokoa kentät useista riveistä (monta genreä/ohjaajaa voi tulla eri riveillä)
    first = rows[0]
    genres = list({r.get("genreLabel", "") for r in rows if r.get("genreLabel")})
    directors = list({r.get("directorLabel", "") for r in rows if r.get("directorLabel")})
    composers = list({r.get("composerLabel", "") for r in rows if r.get("composerLabel")})

    return {
        "title": first.get("itemLabel", film_title),
        "year": first.get("year", ""),
        "wikidata_id": first.get("item", "").split("/")[-1],
        "directors": directors,
        "composers": composers,
        "genres": genres,
    }


# ─── Wikitext-parsijat ───────────────────────────────────────────────────────

def _parse_track_listing(wikitext: str) -> list[TrackEntry]:
    """
    Parsii {{Track listing}} -templaten wikitextistä TrackEntry-listaksi.
    Tukee useita track listing -blokkeja (levy A/B jne.).
    """
    tracks = []

    # Etsi kaikki {{Track listing ... }} -blokit
    # Rakenne: {{Track listing\n| title1 = ...\n| extra1 = ...\n}}
    pattern = re.compile(
        r"\{\{[Tt]rack\s+listing(.*?)\}\}",
        re.DOTALL,
    )

    global_pos = 0  # jatkuva numerointi yli blokkien

    for block_match in pattern.finditer(wikitext):
        block = block_match.group(1)

        # Kerää kaikki title/extra/length -kentät
        fields: dict[str, str] = {}
        for line in block.split("\n"):
            m = re.match(r"\s*\|\s*(\w+)\s*=\s*(.*)", line)
            if m:
                fields[m.group(1).strip()] = m.group(2).strip()

        # Löydä korkein numero
        max_n = 0
        for key in fields:
            m = re.match(r"(?:title|extra|length)(\d+)$", key)
            if m:
                max_n = max(max_n, int(m.group(1)))

        for i in range(1, max_n + 1):
            title = _clean_wikitext(fields.get(f"title{i}", ""))
            artist = _clean_wikitext(fields.get(f"extra{i}", ""))
            length = fields.get(f"length{i}", "")
            if title:
                global_pos += 1
                tracks.append(TrackEntry(
                    position=global_pos,
                    title=title,
                    artist=artist,
                    length=length,
                ))

    return tracks


def _clean_wikitext(text: str) -> str:
    """Poista wikitext-syntaksi: [[linkit]], {{templateit}}, HTML-tagit."""
    # [[Teksti|Näkyvä]] → Näkyvä
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)
    # [[Linkki]] → Linkki
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    # {{template}} pois
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    # HTML-tagit pois
    text = re.sub(r"<[^>]+>", "", text)
    # Ylimääräiset välit
    text = re.sub(r"\s+", " ", text).strip()
    return text
