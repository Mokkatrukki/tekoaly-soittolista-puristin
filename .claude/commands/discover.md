# /discover $ARGUMENTS

Monilähteinen artistihaku. Aja kaikki relevantit API:t annetulle artistille ja kokoa kandidaatit.

`$ARGUMENTS` = artisti tai lyhyt kuvaus, esim. "Nick Cave" tai "Arppa suomi rap"

## Aja tämä koodi

```python
artist_query = "$ARGUMENTS"

from api.lastfm import LastFmClient
from api.discogs import DiscogsClient
from api.musicbrainz import MusicBrainzClient
from api.finnish_charts import FinnishChartsClient
from curator.playlist_builder import PlaylistBuilder

lfm = LastFmClient()
dc = DiscogsClient()
mb = MusicBrainzClient()
charts = FinnishChartsClient()
builder = PlaylistBuilder()

# Last.fm — similar artists
similar = lfm.similar_artists(artist_query, limit=20)
builder.add(similar, source="lastfm_similar", weight=1.5)
print(f"Last.fm similar: {len(similar)} artistia")

# Last.fm — tagit → tag_top_tracks
tags = lfm.artist_tags(artist_query)
top_tags = [t["tag"] for t in tags[:3]]
print(f"Last.fm tagit: {top_tags}")
for tag in top_tags:
    tag_tracks = lfm.tag_top_tracks(tag, limit=20)
    builder.add(tag_tracks, source=f"tag:{tag}", weight=1.0)

# Discogs — producer_graph
try:
    pg = dc.producer_graph(artist_query, max_releases=6)
    print(f"Discogs tuottajat: {[p['name'] for p in pg.get('producers',[])]}")
    for producer in pg.get("producers", []):
        others = producer["other_artists"][:8]
        print(f"  {producer['name']} → {others}")
        for other_artist in others:
            top = lfm.artist_top_tracks(other_artist, limit=5)
            builder.add(top, source=f"producer:{producer['name']}", weight=1.3)
except Exception as e:
    print(f"Discogs producer_graph: {e}")

# MusicBrainz — artist relationships
try:
    mb_results = mb.search_artist(artist_query, limit=1)
    if mb_results:
        info = mb.artist(mb_results[0]["mbid"])
        print(f"MusicBrainz tagit: {info.tags[:5]}")
        print(f"MusicBrainz suhteet: {[(r['type'], r['target_name']) for r in info.relationships[:5]]}")
        for rel in info.relationships:
            if rel["type"] in ("influenced by", "collaboration", "supporting musician"):
                top = lfm.artist_top_tracks(rel["target_name"], limit=5)
                builder.add(top, source=f"mb:{rel['type']}", weight=1.0)
except Exception as e:
    print(f"MusicBrainz: {e}")

# Finnish Charts
try:
    chart_hits = charts.search(artist_query, chart_type="singlet", limit=10)
    builder.add(chart_hits, source="charts", weight=1.2)
    print(f"Charts: {len(chart_hits)} osumaa")
except Exception as e:
    print(f"Charts: {e}")

# Tulokset
ranked = builder.rank(limit=30)
print(f"\n{'='*60}")
print(f"TOP KANDIDAATIT — {artist_query}")
print(f"{'='*60}")
for i, c in enumerate(ranked[:25], 1):
    src = ", ".join(c.sources)
    print(f"{i:2}. {c.artist:30s} — {c.title:35s} [{c.score:.1f}p | {src}]")

print(f"\nYhteensä {len(builder._pool)} uniikkia kandidaattia {len(builder.session['sources'])} lähteestä")
```

## Mitä tehdä tulosten kanssa

Kandidaatit ovat `builder._pool`:ssa ja `ranked`-listassa. Voit jatkaa:
```python
# Lisää manuaalisesti
builder.add_one("Artisti", "Kappale", source="manual", score=2.0)

# Hae Spotify-URI:t ja luo soittolista
from api.spotify import SpotifyClient
sp = SpotifyClient()
uris = builder.resolve(sp, ranked[:20])
url = builder.create(sp, "Soittolistan nimi", uris)
print(url)
```
