# /apis — API-pikaopas

Tässä kaikki wrapperit ja niiden tärkeimmät metodit. Käytä tätä kun unohtuu mitä mistäkin saa.

---

## Spotify — `api/spotify.py`
```python
from api.spotify import SpotifyClient
sp = SpotifyClient()  # OAuth2, avaa selaimen jos ei tokenia

sp.search_tracks("artisti kappale", limit=5, market="FI")
# → [Track(uri, id, name, artist, album, popularity)]

sp.recently_played(limit=20)          # → [Track]  (scope: user-read-recently-played)
sp.top_tracks(limit=20, time_range="medium_term")   # → [Track]
sp.top_artists(limit=20)              # → [{id, name, genres, popularity}]

sp.create_playlist("Nimi", description="")  # → {id, url}
sp.add_tracks(playlist_id, uris)            # splitaa 100 kpl chunkeihin automaattisesti
sp.get_playlist(playlist_id)               # → {id, name, url, tracks}
sp.user_playlists(limit=20)                # → [{id, name, tracks}]

sp.log_summary()  # → JSON API-kutsuista
```
**HUOM:** recommendations, related_artists, audio_features, top_tracks (artistin) = ESTETTY dev-modessa.
Spotify = kohde + käyttäjän oma historia. Discovery tulee muualta.

---

## Last.fm — `api/lastfm.py`
```python
from api.lastfm import LastFmClient
lfm = LastFmClient()

lfm.similar_artists("Nick Cave", limit=20)
# → [SimilarArtist(name, match, mbid, listeners)]

lfm.similar_tracks("artist", "title", limit=15)
# → [SimilarTrack(artist, title, match, mbid)]  — vaatii tarkan nimen

lfm.artist_top_tracks("Arvo Part", limit=20)   # → [SimilarTrack]
lfm.artist_tags("Radiohead")                   # → [{"tag", "count"}]
lfm.track_info("artist", "title")             # → dict (tags, listeners, similar jne.)

lfm.tag_top_tracks("post-punk", limit=20)      # → [SimilarTrack]
lfm.tag_top_artists("dark folk", limit=20)     # → [SimilarArtist]
```
**Paras käyttötapa:** similar_artists + tag_top_tracks. Tag haetaan artist_tags:lla.

---

## Discogs — `api/discogs.py`
```python
from api.discogs import DiscogsClient
dc = DiscogsClient()

dc.search_artist("Väinö Karjalainen", limit=3)  # → [{id, name}]
dc.search_release("dark folk finland", limit=5)  # → [{id, title, year, genres, styles}]
dc.search_master("post-punk 1980s", limit=5)     # → [{id, title, year, genres, styles}]

dc.release(release_id)   # → ReleaseInfo(styles, rating, have, want, tracklist, ...)
dc.master(master_id)     # → ReleaseInfo  (kokoaa kaikki painokset)
dc.artist(artist_id)     # → {id, name, profile, aliases}

dc.artist_releases(artist_id, limit=20)
# → [{id, title, artist, year, type, role, genres, styles}]
# role: "Main" | "Producer" | "Featuring" | ...
# HUOM: sisältää myös releaset joissa artisti on tuottajana!

dc.release_credits(release_id)
# → {producers: [{id, name}], engineers: [...], all_credits: [{id, name, role}]}

dc.producer_graph("Arppa", max_releases=8)
# → {artist, producers: [{name, id, other_artists: ["Ursus Factory", ...]}]}
# Polku: artisti → extraartists (Producer) → tuottajan kaikki releaset → muut artistit
```
**Paras käyttötapa:** styles-kenttä on tarkin genre-signaali. producer_graph löytää "saman tuotantoperheen" artistit.

---

## MusicBrainz — `api/musicbrainz.py`
```python
from api.musicbrainz import MusicBrainzClient
mb = MusicBrainzClient()  # ei API-avainta, rate limit 1 req/s

mb.search_artist("Daft Punk", limit=5)   # → [{mbid, name, type, country, score}]
mb.search_recording("title", artist="", limit=5)  # → [{mbid, title, artist, artist_mbid}]

mb.artist(mbid)
# → ArtistInfo(mbid, name, type, country, tags, begin_year, end_year, relationships)
# relationships: [{type, direction, target_type, target_mbid, target_name}]
# tyypillisiä: "influenced by", "member of", "collaboration"

mb.recording(mbid)
# → RecordingInfo(mbid, title, artist, tags, release_year, relationships)
# relationships: "cover of", "remix of", "samples" jne.

mb.artist_recordings(mbid, limit=25)     # → [{mbid, title, length_ms}]

mb.producer_graph("Arppa", max_recordings=8)
# → {artist, producers: [{name, mbid, other_artists: [...]}]}
# Polku: recordings → artist-rels (producer) → search_recordings(arid=mbid) → artist credits
```
**Paras käyttötapa:** artist.relationships influenced-by/member-of laajentamiseen. producer_graph MusicBrainz-puolelta.

---

## ListenBrainz — `api/listenbrainz.py`
```python
from api.listenbrainz import ListenBrainzClient
lb = ListenBrainzClient()

lb.recommendation_recordings(username="mokkatrukki", limit=25)  # → [{"recording_mbid", "score"}]
lb.user_top_artists(username, limit=20)    # → [{"artist_name", "listen_count"}]
lb.user_top_recordings(username, limit=20) # → [{"track_name", "artist_name"}]
lb.user_listens(username, limit=25)        # → [{"track_name", "artist_name", "listened_at"}]
```
**Huom:** mokkatrukki-tilillä 0 kuuntelua → recommendation_recordings palauttaa tyhjää. Koodi on oikein.

---

## Finnish Charts — `api/finnish_charts.py`
```python
from api.finnish_charts import FinnishChartsClient
charts = FinnishChartsClient()  # paikallinen SQLite, ei verkkoyhteyttä

charts.search("Arppa", chart_type="singlet", year_from=2015, year_to=2025)
# → [ChartEntry(chart_type, year, week, position, artist, title)]
# chart_type: "singlet" | "albumit" | "radio"

charts.top_tracks(chart_type="singlet", year_from=2018, year_to=2024, limit=30)
# → [{artist, title, score, peak_position, total_weeks, years}]
# score = SUM(21 - position) per viikko

charts.top_artists(chart_type="singlet", year_from=2010, year_to=2020, limit=20)
# → [{artist, score, peak_position, unique_titles, total_weeks, years}]

charts.artist_history("Haloo Helsinki!")   # → {artist, total_weeks, peak_position, tracks: [...]}
charts.weekly_chart(year=2023, week=10)    # → [ChartEntry]
```

---

## YLE Areena — `api/yle_areena.py`
```python
from api.yle_areena import YleAreenaClient
areena = YleAreenaClient()

areena.latest_tracks(show_key="yle_x3m", limit=30)
# show_key: "yle_x3m", "ylex", "radio_suomi", "vinyylisalonki", "uuden_musiikin_kilpailu" jne.
# → [{"artist", "title", "show", "episode_id"}]

areena.list_shows()  # → {show_key: {name, id, url, ...}}  (19 tunnettua ohjelmaa)
areena.episode_tracks(episode_id)  # → [{"artist", "title"}]
areena.show_episodes(series_id, limit=5)  # → [{"id", "title", "published"}]
areena.discover_shows()  # skannaa Areena-musikategorian, testaa uudet → hitaahko
```
**Paras käyttötapa:** latest_tracks("yle_x3m") suomalaisen indie/vaihtoehtomusiikin löytämiseen.

---

## PlaylistBuilder — `curator/playlist_builder.py`
```python
from curator.playlist_builder import PlaylistBuilder
builder = PlaylistBuilder()

builder.add(tracks, source="lastfm", weight=1.5)
# tracks: lista diceistä {artist, title}, objekteista joilla .artist/.title, tai (artist, title) -tupleita
builder.add_one("Ursus Factory", "Älä lopeta", source="manual", score=2.0)

ranked = builder.rank(limit=25)         # → [Candidate] pisteytysjärjestyksessä
uris = builder.resolve(sp, ranked)      # hae Spotify-URI:t, palauttaa löydetyt URI:t
url = builder.create(sp, "Nimi", uris)  # luo soittolista Spotifyyn, palauttaa URL:n

print(builder.summary())   # lyhyt tekstiyhteenveto
builder.save_session()     # tallentaa JSON-lokin logs/sessions/
```

## Interviewer — `curator/interviewer.py`
```python
from curator.interviewer import PlaylistIntent, build_strategy, detect_mode, suggest_name

intent = PlaylistIntent(
    mood="melankolia",
    seed_artists=["Nick Cave"],
    seed_genres=["dark folk"],
    mode="expand",   # "normal" | "expand" | "trail" | "escape"
)
strategy = build_strategy(intent)
# strategy.lastfm_artist_seeds, .musicbrainz_explore_relations, .weights, ...

mode = detect_mode("haluaisin löytää jotain uutta tästä genrestä")  # → "expand"
name = suggest_name(intent)  # → "Melankolia Dark folk à la Nick Cave"
```
