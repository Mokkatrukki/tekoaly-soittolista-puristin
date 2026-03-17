"""
Discogs API wrapper.

Mitä Discogsista saadaan soittolistan rakentamiseen:
  search          → hae artisteja/releaseja nimellä → saa Discogs-ID:n
  release         → genres, styles, year, country, tracklist, yhteisöarvosana
  master          → master-release: kaikki painokset koottuna, genres, styles
  artist          → artistin profiili, aliakset
  artist_releases → artistin kaikki julkaisut (filtteröi tyypeittäin)

Arvokkain data:
  - styles (tarkka genre, esim. "Acid House", "Cosmic Disco", "Dungeon Synth")
  - community.rating.average — laatu-indikaattori
  - community.have / community.want — suosio/keräilyarvo
  - year — aikakausi
  - country — alkuperämaa

Autentikaatio: token (DISCOGS_TOKEN ympäristömuuttujassa)
User-Agent vaaditaan: asetetaan automaattisesti
"""

import os
import time
from dataclasses import dataclass

import discogs_client
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")

USER_AGENT = "SoittolistaPuristin/0.1"


# ─── Dataluokat ──────────────────────────────────────────────────────────────

@dataclass
class ReleaseInfo:
    id: int
    title: str
    artist: str
    year: int | None
    country: str
    genres: list[str]
    styles: list[str]          # tarkempi kuin genres
    rating: float              # 0–5 yhteisöarvosana
    have: int                  # kuinka monella on
    want: int                  # kuinka moni haluaa
    tracklist: list[str]       # kappaleiden nimet

    def style_tags(self) -> list[str]:
        """Kaikki genre+style -tagit yhtenä listana, lowercase."""
        return [t.lower() for t in self.genres + self.styles]


@dataclass
class ApiCall:
    endpoint: str
    params: dict
    result_count: int
    latency_ms: float
    error: str | None = None


# ─── Asiakas ─────────────────────────────────────────────────────────────────

class DiscogsClient:
    """
    Discogs-wrapper discogs_client:n päälle.

    Rate limiting: 60 req/min autentikoituneille (token).
    _rate_delay = 1.1s kutsujen välissä — turvallinen tahti.
    Jos tulee 429, lisätään viive automaattisesti.
    """

    _rate_delay: float = 1.1   # sekuntia kutsujen välissä

    def __init__(self) -> None:
        self._d = discogs_client.Client(
            USER_AGENT,
            user_token=os.getenv("DISCOGS_TOKEN"),
        )
        self.call_log: list[ApiCall] = []
        self._last_call: float = 0.0

    def _throttle(self) -> None:
        """Odota tarvittaessa ennen seuraavaa kutsua."""
        elapsed = time.monotonic() - self._last_call
        wait = self._rate_delay - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _fetch_with_retry(self, fn, *args, max_retries: int = 3, **kwargs):
        """Kutsu fn retry-logiikalla 429-virheitä varten."""
        retries = 0
        while True:
            self._throttle()
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                if "429" in str(e) and retries < max_retries:
                    wait = 5 * (retries + 1)
                    time.sleep(wait)
                    retries += 1
                    continue
                raise

    def _time(self, endpoint: str, params: dict, fn, *args, **kwargs):
        t0 = time.monotonic()
        error = None
        result = None
        try:
            result = self._fetch_with_retry(fn, *args, **kwargs)
        except Exception as e:
            error = str(e)
            raise
        finally:
            latency = (time.monotonic() - t0) * 1000
            try:
                count = len(result) if hasattr(result, "__len__") else 1
            except Exception:
                count = 0
            self.call_log.append(ApiCall(
                endpoint=endpoint,
                params=params,
                result_count=count,
                latency_ms=round(latency, 1),
                error=error,
            ))
        return result

    def _iter_results(self, results, limit: int) -> list:
        """Iteroi lazy Discogs-hakutulokset throttlella ja 429-retrylla."""
        out = []
        retries = 0
        while True:
            try:
                self._throttle()
                for r in results:
                    out.append(r)
                    if len(out) >= limit:
                        break
                return out
            except Exception as e:
                if "429" in str(e) and retries < 3:
                    wait = 5 * (retries + 1)
                    time.sleep(wait)
                    retries += 1
                    out = []
                    continue
                raise

    # ─── Haku ────────────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 5, country: str = "") -> list[dict]:
        """Alias search_release:lle. Käytä tätä oletuksena."""
        return self.search_release(query, limit=limit, country=country)

    def search_release(self, query: str, limit: int = 5, country: str = "") -> list[dict]:
        """
        Hae releaseja hakusanalla.
        Palauttaa: [{id, title, year, genres, styles, country, community_have, community_want}]
        community-data tulee search-tuloksista suoraan (ei vaadi ylimääräistä release()-kutsua).
        """
        kwargs: dict = {"type": "release"}
        if country:
            kwargs["country"] = country
        results = self._time(
            "database.search[release]", {"q": query, "limit": limit, **kwargs},
            self._d.search, query, **kwargs,
        )
        out = []
        for r in self._iter_results(results, limit):
            try:
                d = r.data if hasattr(r, "data") and isinstance(r.data, dict) else {}
                comm = d.get("community", {}) or {}
                out.append({
                    "id": r.id,
                    "title": r.title,
                    "year": getattr(r, "year", None),
                    "genres": list(getattr(r, "genres", []) or []),
                    "styles": list(getattr(r, "styles", []) or []),
                    "country": getattr(r, "country", ""),
                    "community_have": int(comm.get("have", 0) or 0),
                    "community_want": int(comm.get("want", 0) or 0),
                })
            except Exception:
                continue
        return out

    def search_japan(self, query: str, limit: int = 5) -> list[dict]:
        """
        Oikotie: search_release jossa country=Japan.
        Käyttö: japanilaisen musiikin haku — suodattaa pois muut versiot.
        Palauttaa samat kentät kuin search_release, aina japanilaiset julkaisut.
        """
        return self.search_release(query, limit=limit, country="Japan")

    def search_artist(self, query: str, limit: int = 5) -> list[dict]:
        """
        Hae artisteja nimellä.
        Palauttaa: [{id, name}]
        """
        results = self._time(
            "database.search[artist]", {"q": query, "type": "artist", "limit": limit},
            self._d.search, query, type="artist",
        )
        out = []
        for r in self._iter_results(results, limit):
            try:
                out.append({
                    "id": r.id,
                    "name": r.name,
                })
            except Exception:
                continue
        return out

    def search_master(self, query: str, limit: int = 5) -> list[dict]:
        """
        Hae master-releaseja. Master kokoaa kaikki painokset yhteen —
        parempi lähtökohta genre/style-tiedolle kuin yksittäinen release.
        """
        results = self._time(
            "database.search[master]", {"q": query, "type": "master", "limit": limit},
            self._d.search, query, type="master",
        )
        out = []
        for r in self._iter_results(results, limit):
            try:
                d = r.data if hasattr(r, "data") and isinstance(r.data, dict) else {}
                comm = d.get("community", {}) or {}
                out.append({
                    "id": r.id,
                    "title": r.title,
                    "year": getattr(r, "year", None),
                    "genres": list(getattr(r, "genres", []) or []),
                    "styles": list(getattr(r, "styles", []) or []),
                    "community_have": int(comm.get("have", 0) or 0),
                    "community_want": int(comm.get("want", 0) or 0),
                })
            except Exception:
                continue
        return out

    # ─── Release ─────────────────────────────────────────────────────────────

    def release(self, release_id: int) -> ReleaseInfo:
        """
        Hae release ID:llä. Paras tapa saada tarkka genre/style-data.
        """
        r = self._time(
            "database.release", {"id": release_id},
            self._d.release, release_id,
        )
        artists = getattr(r, "artists", [])
        artist_name = artists[0].name if artists else "?"

        # community-data on .data-dictissä, ei objektiattribuuteissa
        community_data = {}
        if hasattr(r, "data") and isinstance(r.data, dict):
            community_data = r.data.get("community", {}) or {}
        rating = 0.0
        have = 0
        want = 0
        if community_data:
            rating_dict = community_data.get("rating", {}) or {}
            rating = float(rating_dict.get("average", 0) or 0)
            have = int(community_data.get("have", 0) or 0)
            want = int(community_data.get("want", 0) or 0)

        tracklist = []
        for t in (getattr(r, "tracklist", []) or []):
            title = getattr(t, "title", "")
            if title:
                tracklist.append(title)

        return ReleaseInfo(
            id=r.id,
            title=r.title,
            artist=artist_name,
            year=getattr(r, "year", None),
            country=getattr(r, "country", "") or "",
            genres=list(getattr(r, "genres", []) or []),
            styles=list(getattr(r, "styles", []) or []),
            rating=rating,
            have=have,
            want=want,
            tracklist=tracklist,
        )

    def master(self, master_id: int) -> ReleaseInfo:
        """
        Hae master-release ID:llä.
        Sama rakenne kuin release(), mutta kokoaa kaikki painokset.
        """
        m = self._time(
            "database.master", {"id": master_id},
            self._d.master, master_id,
        )
        artists = getattr(m, "artists", [])
        artist_name = artists[0].name if artists else "?"

        tracklist = []
        for t in (getattr(m, "tracklist", []) or []):
            title = getattr(t, "title", "")
            if title:
                tracklist.append(title)

        return ReleaseInfo(
            id=m.id,
            title=m.title,
            artist=artist_name,
            year=getattr(m, "year", None),
            country="",
            genres=list(getattr(m, "genres", []) or []),
            styles=list(getattr(m, "styles", []) or []),
            rating=0.0,
            have=0,
            want=0,
            tracklist=tracklist,
        )

    def release_credits(self, release_id: int) -> dict:
        """
        Hae releasen henkilöcreditit (extraartists): tuottajat, äänittäjät, miksaajat jne.

        Palauttaa:
        {
          "producers":  [{"id": 123, "name": "Väinö Karjalainen"}],
          "engineers":  [...],
          "all_credits": [{"id", "name", "role"}]
        }

        Discogs-release sisältää 'extraartists'-listan jossa rooli on string kuten
        "Produced By", "Recorded By", "Mixed By", "Written-By" jne.
        """
        r = self._time(
            "database.release.credits", {"id": release_id},
            self._d.release, release_id,
        )
        # Triggeröi täysi datahaku (discogs_client on lazy-loading)
        _ = r.title
        extra = r.data.get("extraartists", []) or []
        producers = []
        engineers = []
        all_credits = []
        for person in extra:
            try:
                # extra voi olla dict (r.data) tai objekti (getattr)
                if isinstance(person, dict):
                    name = person.get("name", "") or ""
                    person_id = person.get("id", None)
                    role = person.get("role", "") or ""
                else:
                    name = getattr(person, "name", "") or ""
                    person_id = getattr(person, "id", None)
                    role = getattr(person, "role", "") or ""
                entry = {"id": person_id, "name": name, "role": role}
                all_credits.append(entry)
                role_lower = role.lower()
                if "produc" in role_lower:
                    producers.append({"id": person_id, "name": name})
                if any(w in role_lower for w in ("engineer", "recorded", "mixed", "mastered")):
                    engineers.append({"id": person_id, "name": name})
            except Exception:
                continue
        return {"producers": producers, "engineers": engineers, "all_credits": all_credits}

    def producer_graph(
        self,
        artist_name: str,
        max_releases: int = 5,
        max_producer_releases: int = 30,
    ) -> dict:
        """
        Tuottajaverkosto Discogsista.

        Arpa → Väinö Karjalainen (extraartist, role="Produced By")
             → Ursus Factory, Nössö Nova (muut artistit joita Väinö on tuottanut)

        Toiminta:
          1. Hae artisti → ID
          2. Hae heidän releaset → extraartists → kerää tuottajat
          3. Per tuottaja: search(name) → releases → kerää pääartistit

        Palauttaa:
        {
          "artist": "Arpa",
          "producers": [
            {
              "name": "Väinö Karjalainen",
              "id": 123,
              "other_artists": ["Ursus Factory", "Nössö Nova", ...]
            }
          ]
        }

        Huom: Discogs-haku indeksoi extraartist-creditit, joten hakeminen tuottajan nimellä
        palauttaa releaset joissa hän esiintyy missä roolissa tahansa.
        """
        # 1. Etsi artisti
        artists = self.search_artist(artist_name, limit=3)
        if not artists:
            return {"artist": artist_name, "producers": [], "error": "Artistia ei löydy"}
        artist_id = artists[0]["id"]
        artist_name_found = artists[0]["name"]

        # 2. Hae artistin releaset ja etsi tuottajat extraartistseista
        releases = self.artist_releases(artist_id, limit=max_releases)
        producers: dict[str, int | None] = {}  # name → discogs_id
        for rel in releases:
            try:
                rel_id = rel["id"]
                rel_type = rel.get("type", "")

                # Jos kyseessä on master-release, hae main release sen sijaan
                # (extraartist-data on releasella, ei masterilla)
                if rel_type == "master" or rel_type == "Master":
                    m = self._d.master(rel_id)
                    main_rel = getattr(m, "main_release", None)
                    if main_rel:
                        rel_id = main_rel.id

                credits = self.release_credits(rel_id)
                for p in credits["producers"]:
                    if p["name"] and p["name"] not in producers:
                        producers[p["name"]] = p["id"]
            except Exception:
                continue

        if not producers:
            return {
                "artist": artist_name_found,
                "producers": [],
                "note": "Ei tuottajacreditejä Discogsissa (releaseilla ei extraartists-dataa)",
            }

        # 3. Per tuottaja: etsi mitä muuta he ovat tuottaneet
        result_producers = []
        for producer_name, producer_id in producers.items():
            # Varmista Discogs-ID: jos extraartistista saatiin ID, käytetään sitä,
            # muuten haetaan artistihaulla
            if not producer_id:
                found = self.search_artist(producer_name, limit=1)
                producer_id = found[0]["id"] if found else None

            if not producer_id:
                result_producers.append({"name": producer_name, "id": None, "other_artists": []})
                continue

            other_artists = self._find_producer_artists(
                producer_id,
                exclude_artist=artist_name_found,
                limit=max_producer_releases,
            )
            result_producers.append({
                "name": producer_name,
                "id": producer_id,
                "other_artists": other_artists,
            })

        return {
            "artist": artist_name_found,
            "artist_id": artist_id,
            "producers": result_producers,
        }

    def _find_producer_artists(
        self,
        producer_id: int,
        exclude_artist: str = "",
        limit: int = 30,
    ) -> list[str]:
        """
        Hae artistit joita tämä tuottaja on tuottanut.

        Discogs pitää tuottajan artist_releases-listassa MYÖS julkaisut joissa
        hän on tuottajana (ei pääartistina). Haetaan kaikki heidän releaset ja
        poimitaan pääartistit niistä joissa tuottaja ei itse ole pääartisti.
        """
        exclude_lower = exclude_artist.lower()
        try:
            releases = self.artist_releases(producer_id, limit=limit)
        except Exception:
            return []

        # Haetaan myös tuottajan oman nimen jotta voidaan filtteröidä pois
        try:
            producer_info = self.artist(producer_id)
            producer_name_lower = producer_info["name"].lower()
        except Exception:
            producer_name_lower = ""

        artists: dict[str, str] = {}  # lowercase → original name
        for r in releases:
            artist = r.get("artist", "") or ""
            artist_lower = artist.lower()
            if (artist and
                    artist_lower != exclude_lower and
                    artist_lower != producer_name_lower and
                    "various" not in artist_lower and
                    artist_lower not in artists):
                artists[artist_lower] = artist

        return list(artists.values())

    # ─── Artisti ─────────────────────────────────────────────────────────────

    def artist(self, artist_id: int) -> dict:
        """
        Artistin perustiedot: nimi, profiili, aliakset.
        """
        a = self._time(
            "database.artist", {"id": artist_id},
            self._d.artist, artist_id,
        )
        return {
            "id": a.id,
            "name": a.name,
            "profile": getattr(a, "profile", "") or "",
            "aliases": [al.name for al in (getattr(a, "aliases", []) or [])],
            "urls": list(getattr(a, "urls", []) or []),
        }

    def artist_releases(
        self,
        artist_id: int,
        limit: int = 20,
        sort: str = "year",          # "year" | "title" | "format"
        sort_order: str = "desc",
    ) -> list[dict]:
        """
        Artistin julkaisut. Sisältää myös julkaisut joissa artisti on tuottajana/yhteistyössä.
        Palauttaa: [{id, title, artist, year, type, role, genres, styles}]

        'role' kertoo miten artisti liittyy tähän releaseen:
          "Main"      = pääartisti
          "Featuring" = featuringinä
          "" / muu    = tuottaja, äänittäjä tms. (extraartist)
        """
        a = self._d.artist(artist_id)
        releases = self._time(
            "database.artist_releases",
            {"artist_id": artist_id, "limit": limit},
            a.releases.page, 1,
        )
        out = []
        for r in list(releases)[:limit]:
            try:
                # artist ja role löytyvät suoraan r.data:sta (ei attribuutteina)
                d = r.data if hasattr(r, "data") else {}
                main_artist = d.get("artist", "") or ""
                role = d.get("role", "") or ""
                out.append({
                    "id": r.id,
                    "title": r.title,
                    "artist": main_artist,
                    "year": d.get("year") or getattr(r, "year", None),
                    "type": d.get("type", "") or getattr(r, "type", ""),
                    "role": role,
                    "genres": list(getattr(r, "genres", []) or []),
                    "styles": list(getattr(r, "styles", []) or []),
                })
            except Exception:
                continue
        return out

    # ─── Loki ────────────────────────────────────────────────────────────────

    def log_summary(self) -> dict:
        return {
            "total_calls": len(self.call_log),
            "total_latency_ms": round(sum(c.latency_ms for c in self.call_log), 1),
            "calls": [
                {
                    "endpoint": c.endpoint,
                    "params": c.params,
                    "results": c.result_count,
                    "latency_ms": c.latency_ms,
                    **({"error": c.error} if c.error else {}),
                }
                for c in self.call_log
            ],
        }
