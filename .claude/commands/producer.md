# /producer $ARGUMENTS

Etsi artisti → löydä tuottajat → löydä mitä muuta he ovat tuottaneet.

`$ARGUMENTS` = artisti jonka tuottajaverkostoa halutaan tutkia, esim. "Arppa" tai "Ursus Factory"

## Aja tämä koodi

```python
artist_query = "$ARGUMENTS"

from api.discogs import DiscogsClient
from api.musicbrainz import MusicBrainzClient
from api.lastfm import LastFmClient
from curator.playlist_builder import PlaylistBuilder

dc = DiscogsClient()
mb = MusicBrainzClient()
lfm = LastFmClient()

# ── Discogs producer_graph ──────────────────────────────────────────────────
print(f"=== Discogs: {artist_query} tuottajaverkosto ===")
try:
    pg = dc.producer_graph(artist_query, max_releases=8, max_producer_releases=30)
    print(f"Artisti: {pg['artist']}")

    if not pg.get("producers"):
        print(f"Huom: {pg.get('note', 'Ei tuottajatietoja')}")
    else:
        for p in pg["producers"]:
            others = p["other_artists"]
            print(f"\nTuottaja: {p['name']} (Discogs id {p['id']})")
            print(f"  Muut artistit ({len(others)}):")
            for name in others[:15]:
                print(f"    - {name}")
except Exception as e:
    print(f"Discogs virhe: {e}")

# ── MusicBrainz producer_graph ──────────────────────────────────────────────
print(f"\n=== MusicBrainz: {artist_query} tuottajaverkosto ===")
try:
    mb_pg = mb.producer_graph(artist_query, max_recordings=8)
    if mb_pg.get("producers"):
        for p in mb_pg["producers"]:
            print(f"\nTuottaja: {p['name']} (mbid {p['mbid'][:8]})")
            print(f"  Muut artistit: {p['other_artists'][:10]}")
    else:
        print(f"Huom: {mb_pg.get('note', 'Ei tuottajatietoja MusicBrainzissa')}")
except Exception as e:
    print(f"MusicBrainz virhe: {e}")

# ── Kerää kandidaatit PlaylistBuilderiin ────────────────────────────────────
print(f"\n=== Kerätään kappaleet tuottajaverkoston artisteilta ===")
builder = PlaylistBuilder()

# Yhdistä molemmat lähteet
all_network_artists = set()
try:
    for p in pg.get("producers", []):
        all_network_artists.update(p["other_artists"][:10])
except Exception:
    pass
try:
    for p in mb_pg.get("producers", []):
        all_network_artists.update(p["other_artists"][:10])
except Exception:
    pass

print(f"Verkoston artistit ({len(all_network_artists)}): {list(all_network_artists)[:10]}")

for artist_name in list(all_network_artists)[:15]:
    try:
        top = lfm.artist_top_tracks(artist_name, limit=5)
        builder.add(top, source="producer_network", weight=1.3)
    except Exception:
        pass

ranked = builder.rank(limit=30)
if ranked:
    print(f"\nTop kandidaatit tuottajaverkostosta:")
    for i, c in enumerate(ranked[:20], 1):
        print(f"  {i:2}. {c.artist} — {c.title} [{c.score:.1f}p]")
```

## Vinkki: tunnettu tuottaja suoraan

Jos tiedät tuottajan nimen valmiiksi, voit hakea suoraan hänen verkostonsa:
```python
from api.discogs import DiscogsClient
dc = DiscogsClient()
artists = dc.search_artist("Väinö Karjalainen", limit=1)
releases = dc.artist_releases(artists[0]["id"], limit=30)
# releases sisältää kaikki releaset joissa hän on mukana (myös tuotannot)
for r in releases:
    print(f"[{r['role']}] {r['artist']} — {r['title']}")
```
