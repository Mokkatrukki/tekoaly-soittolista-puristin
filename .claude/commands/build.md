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

# Discogs — käynnistä TAUSTALLE ennen Last.fm-hakuja (1.2s/kutsu — ei saa blokata)
# Validointi: album want-luvut laadun indikaattorina
discogs_futures = {}
if strategy.discogs_albums_to_validate:
    discogs_futures = dc.search_background([
        (f"{artist} {album}", 2)
        for artist, album in strategy.discogs_albums_to_validate[:8]
    ])
# producer_graph (trail/expand -moodi) — tämäkin taustalle jos mahdollista
if strategy.discogs_search_query:
    pg = dc.producer_graph(strategy.discogs_search_query)
    for producer in pg.get("producers", []):
        for artist_name in producer["other_artists"][:10]:
            top = lfm.artist_top_tracks(artist_name, limit=5)
            builder.add(top, source="discogs_producer_network", weight=strategy.weights["discogs"])

# ... (Last.fm-haut) ...

# Nouda Discogs-tulokset lopussa (blokkaa vain jos ei vielä valmis)
for query, fut in discogs_futures.items():
    for r in fut.result():
        # want > 500 = merkittävä, > 2000 = klassikko
        if r["community_want"] > 500:
            builder.boost(r["title"], bonus=r["community_want"] / 1000)

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

## API-wrapperit — oikea käyttö

### LastFmClient
```python
from api.lastfm import LastFmClient
lfm = LastFmClient()

# similar_artists palauttaa SimilarArtist-objekteja, EI dict:ejä
similar = lfm.similar_artists("Ben Howard", limit=20)
for a in similar:
    print(a.name, a.match)   # ← .name ja .match, EI a["name"]

# artist_top_tracks palauttaa dict-listaa: [{title, artist, playcount}]
tracks = lfm.artist_top_tracks("Ben Howard", limit=5)
for t in tracks:
    print(t["title"], t["playcount"])

# artist_listeners — kuuntelijamäärä suosio-indikaattorina
n = lfm.artist_listeners("Ben Howard")

# artist_tags — genre-signaali
tags = lfm.artist_tags("Ben Howard", limit=5)   # → ["folk", "singer-songwriter", ...]
```

### DiscogsClient
```python
from api.discogs import DiscogsClient
dc = DiscogsClient()

# ⚠️ DISCOGS ON HIDAS (1.2s/kutsu) — käytä AINA search_background() niin se ei blokkaa!

# ✅ OIKEA TAPA: käynnistä taustalle heti, tee Last.fm-haut sen aikana
futures = dc.search_background([
    ('Burial Untrue', 3),
    ('Jon Hopkins Immunity', 2),
    ('Boards of Canada Music Has the Right to Children', 2),
])
# Last.fm ja Spotify -haut tässä välissä — Discogs pyörii taustalla
similar = lfm.similar_artists('Burial', limit=20)
tag_tracks = lfm.tag_top_tracks('ambient', limit=20)
# Nouda tulokset vasta kun tarvitaan
for query, fut in futures.items():
    results = fut.result()
    for r in results:
        print(r["title"], r["community_want"])

# Synkroninen haku (vain jos YKSI kutsu eikä muuta tehtävää sen aikana)
results = dc.search("Damien Rice O", limit=3)
# → [{id, title, year, genres, styles, country, community_have, community_want}]

# Laadun kynnykset:
#   community_want > 2000 → klassikko ★★★
#   community_want > 500  → merkittävä ★★
#   community_want > 100  → hyvä ★
#   < 100                 → heikko signaali

# search_master — albumi-tasolla, EI yksittäisiä painoksia (parempi genre-data)
masters = dc.search_master("Iron & Wine", limit=5)
# → [{id, title, year, genres, styles, community_have, community_want}]
```

### SpotifyClient
```python
from api.spotify import SpotifyClient
sp = SpotifyClient()

# Sisäinen asiakas: sp._sp (ei sp.sp)
# Kappaleiden haku Spotify-URI:a varten
tracks = sp.search_tracks("Ben Howard Conrad", limit=3)
for t in tracks:
    print(t.artist, t.name, t.uri)

# Soittolistan hallinta
sp.add_tracks(playlist_id, [uri1, uri2])
sp.remove_tracks(playlist_id, [uri1])
tracks = sp.get_playlist_tracks(playlist_id)
```
