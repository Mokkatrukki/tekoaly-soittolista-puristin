"""
PlaylistInterviewer — haastattelu + API-strategian rakentaminen.

Tärkeintä ei ole noudattaa tiukkaa skriptaa vaan ymmärtää mitä käyttäjä haluaa.
Tunnelma ja tilanne ovat yhtä hyviä lähtökohtia kuin artisti tai genre.
Käyttäjä voi tietää tarkalleen mitä haluaa, tai vain fiilisen.
Molemmat ovat hyviä lähtökohtia.

Käyttö:
    intent = PlaylistIntent(
        mood="melankolia",
        seed_artists=["Nick Cave"],
        seed_genres=["dark folk"],
        mode="expand",
    )
    strategy = build_strategy(intent)
    # strategy.weights, strategy.lastfm_artist_seeds jne.
"""

from dataclasses import dataclass, field


# ─── Käyttäjän toiveet ────────────────────────────────────────────────────────

@dataclass
class PlaylistIntent:
    """
    Kaikki mitä haastattelusta selvisi.

    Ei tarvitse täyttää kaikkia kenttiä — puuttuva tieto on OK.
    Moodi vaikuttaa siihen, mitä API-lähteitä painotetaan.

    Moodit:
        normal  käyttäjä tietää mitä haluaa (genre / artisti / tunnelma)
        expand  tuttu alue, haluaa laajentaa viereisiin
        trail   uteliaisuuspolku yksityiskohdassa (esim. "Trent Reznor elokuvissa")
        escape  haluaa ulos omasta kuplastaan, ankkuri on tunnelma tai yksi tuttu piste
    """
    description: str = ""           # käyttäjän kuvaus omin sanoin
    mood: str = ""                  # tunnelma / fiilis
    situation: str = ""             # ajomusa, bilemusaa, taustamusiikki, keskittyminen...

    seed_artists: list[str] = field(default_factory=list)   # referenssiartistit
    seed_tracks: list[str] = field(default_factory=list)    # referenssikappaleet
    seed_genres: list[str] = field(default_factory=list)    # genret / tyylit

    avoid: list[str] = field(default_factory=list)          # mitä EI haluta
    era: tuple[int, int] = (1950, 2025)                     # aikakausi

    finnish_only: bool = False      # pelkkä suomimusiikki?
    track_count: int = 20           # soittolistan pituus
    playlist_name: str = ""         # ehdotettu nimi (voi jättää tyhjäksi → suggest_name)

    mode: str = "normal"


# ─── API-strategia ────────────────────────────────────────────────────────────

@dataclass
class ApiStrategy:
    """
    Mitä API-kutsuja tehdään ja millä painoilla.
    PlaylistBuilder.add() käyttää weights-arvoja.
    """
    lastfm_artist_seeds: list[str] = field(default_factory=list)
    lastfm_tags: list[str] = field(default_factory=list)

    musicbrainz_artists: list[str] = field(default_factory=list)
    musicbrainz_explore_relations: bool = False  # trail-moodi: suhde-navigointi

    discogs_styles: list[str] = field(default_factory=list)
    discogs_search_query: str = ""

    charts_query: str = ""
    charts_era: tuple[int, int] = (2000, 2025)
    charts_enabled: bool = True

    areena_enabled: bool = True

    spotify_personalization: bool = True  # recently_played + top_artists

    weights: dict = field(default_factory=lambda: {
        "lastfm_similar_artists": 1.5,
        "lastfm_similar_tracks": 1.2,
        "lastfm_tags": 1.0,
        "musicbrainz": 1.0,
        "discogs": 0.8,
        "charts": 1.3,
        "areena": 1.0,
        "spotify_personal": 1.8,
    })


# ─── Strategian rakentaminen ──────────────────────────────────────────────────

def build_strategy(intent: PlaylistIntent) -> ApiStrategy:
    """
    Muuntaa PlaylistIntentin API-strategiaksi.

    Moodit vaikuttavat painotuksiin:
        normal   tasapainoinen kaikkien lähteiden käyttö
        expand   MusicBrainz-suhteet ja Discogs-tyylit korostuvat
        trail    MusicBrainz-suhde-navigointi pääpainossa
        escape   tunnelma Last.fm-tageissa pääpainossa, ei personalisointia
    """
    s = ApiStrategy()

    s.lastfm_artist_seeds = intent.seed_artists[:]
    s.musicbrainz_artists = intent.seed_artists[:]
    s.discogs_styles = intent.seed_genres[:]

    # Charts-aikakausi: SQLite-data alkaa 2000:sta
    era_start = max(intent.era[0], 2000)
    s.charts_era = (era_start, intent.era[1])
    s.charts_enabled = intent.finnish_only or bool(intent.seed_genres) or bool(intent.seed_artists)

    # Last.fm -tagit: genret + tunnelma + tilanne
    tags = list(intent.seed_genres)
    if intent.mood:
        tags.append(intent.mood)
    s.lastfm_tags = tags

    # Discogs-haku: artisti + genre tai pelkkä genre
    if intent.seed_artists and intent.seed_genres:
        s.discogs_search_query = f"{intent.seed_artists[0]} {intent.seed_genres[0]}"
    elif intent.seed_genres:
        s.discogs_search_query = intent.seed_genres[0]
    elif intent.seed_artists:
        s.discogs_search_query = intent.seed_artists[0]

    # Charts-hakusana
    if intent.seed_artists:
        s.charts_query = intent.seed_artists[0]
    elif intent.seed_genres:
        s.charts_query = intent.seed_genres[0]

    # Moodikohtaiset painot
    if intent.mode == "expand":
        # Tuttu alue, haetaan viereisiä — suhteet ja tyylit korostuvat
        s.musicbrainz_explore_relations = True
        s.weights["musicbrainz"] = 1.8
        s.weights["discogs"] = 1.5
        s.weights["lastfm_tags"] = 1.3
        s.weights["spotify_personal"] = 0.8  # historia painottuu vähemmän

    elif intent.mode == "trail":
        # Uteliaisuuspolku — MusicBrainz-yhteydet pääpainossa
        s.musicbrainz_explore_relations = True
        s.weights["musicbrainz"] = 2.0
        s.weights["discogs"] = 1.5
        s.weights["lastfm_similar_artists"] = 1.0
        s.weights["spotify_personal"] = 0.5

    elif intent.mode == "escape":
        # Kupla-pako — ei personalisointia, tunnelma ankkurina
        s.spotify_personalization = False
        s.weights["spotify_personal"] = 0.0
        s.weights["lastfm_tags"] = 2.0
        s.weights["lastfm_similar_artists"] = 1.5
        s.weights["charts"] = 0.5  # tutut listat eivät auta ulos kuplasta

    return s


# ─── Moodin tunnistaminen ─────────────────────────────────────────────────────

# Käyttäjän vastauksista tunnistettavia vihjeitä moodiin
_MODE_HINTS = {
    "expand": [
        "olen jo aika perehtynyt", "tiedän tän tyylin hyvin", "haluaisin löytää jotain uutta",
        "loppuu kesken", "samaa mutta eri", "mitä muuta tähän liittyy",
        "syvemmälle", "pidemmälle", "laajemmin",
    ],
    "trail": [
        "olen kuullut että", "haluaisin tietää enemmän", "liittyy johonkin",
        "soundtrackit", "yhteistyöprojektit", "sivuprojektit", "vaikutteet",
        "mistä tämä on peräisin", "millainen historia", "kuka on mukana",
    ],
    "escape": [
        "jotain täysin erilaista", "eri kulttuuri", "en tunne", "haluaisin tutustua",
        "ulos mukavuusalueelta", "kokeilu", "eri maailma", "ei normaalia",
        "haaste", "ylläty minut",
    ],
}


def detect_mode(description: str) -> str:
    """
    Arvailee moodin käyttäjän kuvauksen perusteella.
    Palauttaa 'normal' jos mikään ei tunnistu.
    """
    desc_lower = description.lower()
    for mode, hints in _MODE_HINTS.items():
        if any(hint in desc_lower for hint in hints):
            return mode
    return "normal"


# ─── Soittolistan nimen ehdotus ───────────────────────────────────────────────

def suggest_name(intent: PlaylistIntent) -> str:
    """Ehdottaa soittolistan nimeä intentin pohjalta."""
    parts = []
    if intent.mood:
        parts.append(intent.mood.capitalize())
    if intent.seed_genres:
        parts.append(intent.seed_genres[0].capitalize())
    if intent.seed_artists:
        parts.append(f"à la {intent.seed_artists[0]}")
    if intent.situation:
        parts.append(f"— {intent.situation}")
    if not parts and intent.description:
        # Lyhennä kuvaus 40 merkkiin
        parts.append(intent.description[:40].rstrip())
    return " ".join(parts) if parts else "Soittolista"


# ─── Haastatteluopas ─────────────────────────────────────────────────────────

# Ei tiukka skripti — ilmapiiri. Claude käyttää näitä vapaamuotoisesti.
# Tärkeintä: kysy tunnelma/tilanne ENSIN, ei genre — toimii myös silloin
# kun käyttäjä ei tiedä mitä haluaa tai haluaa poistua omasta kuplastaan.

INTERVIEW_GUIDE = """
Haastattelun ilmapiiri
─────────────────────
Tavoite: ymmärtää mitä käyttäjä haluaa tunteellisesti ja tilanteen kannalta,
ei vain lista genrejä tai artisteja.

Hyviä aloituskysymyksiä (valitse tilanne mukaan):
  • Minkälaiseen tilanteeseen tai tunnelmaan tämä soittolista on?
  • Mitä haet tänä hetkenä — energia, tunnelma, tausta vai jotain muuta?

Kun tunnelma on selvä, tarkenna:
  • Onko joku artisti, kappale tai levy joka kuvaa hyvin mitä haet?
  • Mitä olet viime aikoina kuunnellut jota haluaisit enemmän?

Laajuus ja rajat:
  • Haluatko pysyä tutussa maastossa, laajentaa viereisiin, vai kokeilla jotain uutta?
  • Onko jotain mitä ehdottomasti EI haluta?
  • Onko suomalainen musiikki tärkeää, tai tietty aikakausi?

Moodin merkkejä:
  expand  "tiedän tän jo hyvin", "haluaisin löytää jotain uutta samasta", "loppuu kesken"
  trail   "olen kuullut että...", "liittyy johonkin", "soundtrackit", "vaikutteet"
  escape  "jotain täysin erilaista", "eri kulttuuri", "haasta minut", "ylläty minut"

Hyvä soittolista syntyy kun tiedetään:
  1. Tunnelma tai tilanne (tärkein)
  2. Yksi tai pari referenssipistettä (artisti, kappale, genre)
  3. Mitä EI haluta
"""
