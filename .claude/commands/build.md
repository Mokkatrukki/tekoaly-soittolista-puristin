# /build — Rakenna soittolista

Käynnistä koko playlist-työnkulku alusta loppuun.

## Työnkulku

### 1. Haastattelu
Kysy käyttäjältä seuraavat asiat (ei tiukkaa järjestystä, vapaamuotoinen keskustelu):
- **Tunnelma/tilanne** ensin — tämä toimii ankkurina myös silloin kun käyttäjä ei tiedä tarkalleen mitä haluaa
- **Referenssipisteet** — artisti, kappale, levy tai genre
- **Mitä EI haluta**
- **Laajuus** — tuttu maasto, laajentaminen viereisiin, vai jotain täysin uutta?
- **Suomimusiikki?** — tärkeä koska meillä on charts-data ja Areena
- **Aikakausi?** — vuosikymmen tai aikaväli
- **Kappaleiden määrä** — oletus 20

Rakenna `PlaylistIntent` vastausten pohjalta ja tunnista moodi:
- `normal` — tietää mitä haluaa
- `expand` — tuttu alue, haluaa laajentaa ("loppuu kesken", "tiedän jo hyvin")
- `trail` — uteliaisuuspolku ("vaikutteet", "soundtrackit", "yhteistyöt")
- `escape` — haluaa ulos kuplasta ("jotain täysin erilaista", "eri kulttuuri")

### 2. API-strategia
```python
from curator.interviewer import PlaylistIntent, build_strategy
intent = PlaylistIntent(...)
strategy = build_strategy(intent)
```

### 3. Haku (aja kaikki relevantti, skippauksella jos tulos tyhjä)

```python
from api.lastfm import LastFmClient
from api.discogs import DiscogsClient
from api.musicbrainz import MusicBrainzClient
from api.finnish_charts import FinnishChartsClient
from api.yle_areena import YleAreenaClient
from api.spotify import SpotifyClient
from curator.playlist_builder import PlaylistBuilder

lfm = LastFmClient()
dc = DiscogsClient()
mb = MusicBrainzClient()
charts = FinnishChartsClient()
areena = YleAreenaClient()
sp = SpotifyClient()
builder = PlaylistBuilder()

# Last.fm — similar artists (kaikki moodit)
for artist in strategy.lastfm_artist_seeds:
    similar = lfm.similar_artists(artist, limit=20)
    builder.add(similar, source="lastfm_similar", weight=strategy.weights["lastfm_similar_artists"])

# Last.fm — tag-pohjainen (kun tunnelma/genre tiedossa)
for tag in strategy.lastfm_tags:
    tag_tracks = lfm.tag_top_tracks(tag, limit=20)
    builder.add(tag_tracks, source=f"lastfm_tag_{tag}", weight=strategy.weights["lastfm_tags"])

# Discogs — producer_graph (trail/expand -moodi tai jos tuottaja mainittu)
if strategy.discogs_search_query:
    pg = dc.producer_graph(strategy.discogs_search_query)
    for producer in pg.get("producers", []):
        for artist_name in producer["other_artists"][:10]:
            top = lfm.artist_top_tracks(artist_name, limit=5)
            builder.add(top, source="discogs_producer_network", weight=strategy.weights["discogs"])

# MusicBrainz — suhteet (expand/trail)
if strategy.musicbrainz_explore_relations:
    for artist in strategy.musicbrainz_artists:
        results = mb.search_artist(artist, limit=1)
        if results:
            info = mb.artist(results[0]["mbid"])
            for rel in info.relationships:
                if rel["type"] in ("influenced by", "collaboration"):
                    top = lfm.artist_top_tracks(rel["target_name"], limit=5)
                    builder.add(top, source="mb_relations", weight=strategy.weights["musicbrainz"])

# Finnish Charts (jos suomimusiikki tai kotimaiset artistit)
if strategy.charts_enabled and strategy.charts_query:
    chart_tracks = charts.top_tracks(year_from=strategy.charts_era[0], year_to=strategy.charts_era[1])
    builder.add(chart_tracks, source="charts", weight=strategy.weights["charts"])

# YLE Areena — suomalainen indie/vaihtoehto
if strategy.areena_enabled:
    areena_tracks = areena.latest_tracks("yle_x3m", limit=30)
    builder.add(areena_tracks, source="areena_x3m", weight=strategy.weights["areena"])

# Spotify — käyttäjän oma historia
if strategy.spotify_personalization:
    top = sp.top_tracks(limit=20)
    builder.add(top, source="spotify_personal", weight=strategy.weights["spotify_personal"])
```

### 4. Rakenna ja luo soittolista
```python
ranked = builder.rank(limit=30)

# Näytä top-20 käyttäjälle ennen luontia
for i, c in enumerate(ranked[:20], 1):
    print(f"{i:2}. {c.artist} — {c.title} [{c.score:.1f}p, {', '.join(c.sources)}]")

# Kysy hyväksyntä / muokkaukset
# ...

uris = builder.resolve(sp, ranked[:20])
url = builder.create(sp, suggest_name(intent), uris)
builder.save_session()

print(f"Soittolista valmis: {url}")
print(builder.summary())
```

## Muistettavaa
- Spotify ei anna recommendations/related_artists — discovery tulee Last.fm + MusicBrainz + Discogs
- Discogs producer_graph on vahva työkalu suomalaisen indie-verkoston löytämiseen
- PlaylistBuilder deduplicoi automaattisesti: sama kappale useasta lähteestä → korkeampi pistemäärä
- `escape`-moodissa `strategy.spotify_personalization = False` — historia ei auta kuplapakossa
