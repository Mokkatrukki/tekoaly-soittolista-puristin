# Soittolista-puristin — Build Log

## Idea
Claude Code -härveli joka kuuntelee mitä soittolistaa haluat, kyselee tarkentavia kysymyksiä,
hakee dataa useista rajapinnoista (Spotify, Last.fm, Discogs, MusicBrainz, ListenBrainz, YLE Areena)
ja rakentaa soittolistan Spotifyyn. Ei MCP — Claude käyttää rajapintoja suoraan session aikana.

## Arkkitehtuuri

```
tekoäly-soittolista-puristin/
├── .env                      # API-avaimet (gitignore)
├── pyproject.toml
├── CLAUDE.md                 # Ohjeet Claudelle
├── LETSBUILD.md              # Tämä tiedosto — build log
│
├── tools/
│   └── fetch_doc.py          # Hakee + parsii API-dokumentaation URL:sta
│
├── api/
│   ├── sources.py            # Nimetyt doc-URL:t per API
│   ├── spotify.py
│   ├── lastfm.py
│   ├── discogs.py
│   ├── musicbrainz.py
│   ├── listenbrainz.py
│   └── yle_areena.py
│
├── curator/
│   ├── interviewer.py        # Vuoropuhelu käyttäjän kanssa
│   └── playlist_builder.py  # Kokoaa soittolistan
│
└── logs/
    └── sessions/             # JSON-logit sessioittain (gitignore)
```

## Valmiit osat

### [2026-03-17] Projektin pohja + doc-fetcher työkalu
- `pyproject.toml`, `.gitignore`, `LETSBUILD.md`, git init (mokkatrukki@gmail.com, main)
- `.claude/commands/checkpoint.md` — `/checkpoint` skill
- `api/sources.py` — nimetyt URL:t kaikille API-endpointeille (Spotify, Last.fm, Discogs, MusicBrainz, ListenBrainz, YLE Areena)
- `tools/fetch_doc.py` — hakee API-dokumentaation URL:sta tai nimetystä avaimesta, palauttaa siistin tekstin + token-arvion
- `tools/distill.py` — kohinanpoistaja: boilerplate pois, param-formaatti siistiksi, aggressive-moodi ~178 tok vs ~3800 tok normaali
- Spotify-dokumentaatio kartoitettu: deprecated endpointit merkitty (recommendations, vanhat playlist-endpointit), audio_features toimii
- Huomio: Spotify-sivut ovat sanatariseen verboosia, fetch toimii trafilaturalla ilman JS-renderöintiä

### [2026-03-17] api/spotify.py + distill-parannukset
- `SpotifyClient` — wrapper spotipy:n päälle, lokkaa kaikki kutsut (`call_log`)
- `Track`, `AudioFeatures` dataluokat
- Metodit: `search_tracks`, `search_artists`, `artist_top_tracks`, `related_artists`, `artist_info`, `audio_features`, `recommendations`, `available_genre_seeds`, `create_playlist`, `add_tracks`
- `add_tracks` splitaa automaattisesti 100 kpl chunkeihin
- `log_summary()` palauttaa session API-kutsut JSON-yhteenvetona
- `distill.py`: deprecated-tarkistus korjattu (raakasisältö vs kenttätaso), Spotify legal boilerplate poistettu noiselistasta
- Huomio: `recommendations` on deprecated mutta Spotify ilmaisee sen vain UI-badgellä, ei tekstissä — merkitty koodissa manuaalisesti

### [2026-03-17] Spotify API -kartoitus + soittolistan hallinta
- Lisätty: `remove_tracks`, `reorder_track`, `get_playlist`, `get_playlist_tracks`, `user_playlists`, `find_playlist_by_name`
- Lisätty: `recently_played`, `top_tracks`, `top_artists` (scopet: user-read-recently-played, user-top-read, playlist-read-private)
- Kartoitettu käytännössä mitkä endpointit toimivat Development mode -applikaatiolla

**KRIITTINEN LÖYDÖS: Spotify on blokannut discovery-endpointit Development mode -applikaatioilta**
- ❌ `/recommendations` — poistettu (404)
- ❌ `/artists/{id}/related-artists` — estetty (403)
- ❌ `/artists/{id}/top-tracks` — estetty (403)
- ❌ `/audio-features` — estetty (403)
- ❌ `/recommendations/available-genre-seeds` — poistettu (404)

**Toimii ✓**
- ✅ `search` (tracks + artists)
- ✅ `recently_played`, `top_tracks`, `top_artists` (käyttäjän oma data)
- ✅ Soittolistan hallinta: `create_playlist`, `add_tracks`, `remove_tracks`, `user_playlists`

**Arkkitehtuurivaikutus:** Spotify = kohde + personalisointilähde. Discovery tulee kokonaan Last.fm + MusicBrainz + ListenBrainzista.

### [2026-03-17] fetch_doc Playwright-fallback + api/lastfm.py
- `fetch_doc` saa nyt JS-renderöidyt sivut (Playwright → trafilatura): trafilatura → httpx → Playwright
- `distill` aggressive-fallback: jos >85% sisällöstä poistuisi, palautetaan alkuperäinen
- `api/lastfm.py`: `similar_tracks`, `similar_artists`, `artist_top_tracks`, `artist_tags`, `track_info`, `tag_top_tracks`, `tag_top_artists`
- Testattu: similar_artists, artist_tags, tag_top_tracks toimivat hyvin
- Huomio: `similar_tracks` vaatii tarkan kappaleen nimen — joillakin kappaleilla ei riittävästi dataa

### [2026-03-17] api/discogs.py + api/musicbrainz.py + api/listenbrainz.py + api/yle_areena.py
- `api/discogs.py`: `DiscogsClient` — search_release, search_artist, search_master, release, master, artist, artist_releases. `ReleaseInfo` dataluokka: styles (tarkin genre-signaali), rating, have/want, tracklist. Testattu toimivaksi.
- `api/musicbrainz.py`: `MusicBrainzClient` — search_recording, search_artist, recording (suhteet: cover of, remix of jne.), artist (member-of, influenced-by), artist_recordings. Ei API-avainta — User-Agent asetettu. Testattu: Daft Punk 1993–2021, jäsenet, tagit.
- `api/listenbrainz.py`: `ListenBrainzClient` — recommendation_recordings (ML-suositukset), user_listens, user_top_artists, user_top_recordings. Huomio: mokkatrukki-tilillä 0 kuuntelua, testi palauttaa tyhjää — koodi on oikein.
- `api/yle_areena.py`: `YleAreenaClient` — list_shows, show_episodes, episode_tracks, latest_tracks. Kappalelistan parsinta 3 formaatille (BIISILISTA-otsikko, Artisti - Kappale rivit, Artisti: Kappale). 19 tunnettua musiikkiohjelmaa MUSIC_SHOWS-sanakirjassa. `discover_shows()` testaa automaattisesti uusia ohjelmia Areenan musiikin kategorisivulta.
- `direnv` käyttöön: `.envrc` aktivoi venv automaattisesti projektin kansiossa
- `musicbrainzngs` ja `liblistenbrainz` lisätty venv:iin

### [2026-03-17] api/finnish_charts.py — IFPI Suomi -listatietokanta
- `data/ifpi_charts.db` kopioitu soittolista-suosittelija-projektista (19M, gitignore)
- 155 000 riviä: singlet + albumit + radio, 2000–2025
- `FinnishChartsClient`: `search`, `top_tracks`, `top_artists`, `artist_history`, `weekly_chart`
- Pisteytysmalli: sija 1 = 20 pistettä/viikko, sija 20 = 1 piste/viikko
- Ei verkkoyhteyttä — kaikki kyselyt paikalliseen SQLite:hen

### [2026-03-17] curator/playlist_builder.py — koko putki toimii
- `PlaylistBuilder`: `add(tracks, source, weight)`, `rank(limit)`, `resolve(spotify, candidates)`, `create(spotify, name, uris)`, `save_session()`
- Pisteytysmalli: lineaarinen lasku lähteen sisällä + painokerroin per lähde
- Deduplikaatio normalisoinnilla: lowercase + erikoismerkit pois
- `_extract()` tukee dict/dataluokka/tuple -formaatteja — toimii kaikkien API-wrapperien kanssa
- `save_session()` tallentaa JSON-lokin `logs/sessions/`-kansioon
- Korjattu: `create_playlist` käyttää nyt `current_user_playlist_create` (`/v1/me/playlists`) eikä `user_playlist_create` (`/v1/users/{id}/playlists`) — jälkimmäinen antaa 403
- Testattu: 20/20 löytyi Spotifysta, soittolista luotu onnistuneesti

### [2026-03-17] curator/interviewer.py — haastattelu + API-strategia

Inspiraationa Alice Labs/Solita "Embracing User Unpredictability" (2022) — ei tiukka implementaatio vaan yleisilmapiiri:
- Tunnelma ja tilanne ensin, ei genre
- Käyttäjä voi olla eri "moodeissa": normal / expand / trail / escape

**`PlaylistIntent`** — kaikki mitä haastattelusta selvisi (mood, situation, seed_artists, seed_genres, era, mode, ...)
**`ApiStrategy`** — mitä API-kutsuja tehdään millä painoilla (lastfm_artist_seeds, musicbrainz_explore_relations, weights, ...)
**`build_strategy(intent)`** — muuntaa intentin strategiaksi moodin mukaan:
- expand: MusicBrainz-suhteet + Discogs-tyylit korostuvat, historia painottuu vähemmän
- trail: MusicBrainz pääpainossa (suhde-navigointi), esim. "artistin elokuvasoundtrackit"
- escape: ei Spotify-personalisointia, Last.fm-tagit tunnelma-ankkurina
**`detect_mode(description)`** — arvailee moodin käyttäjän sanoista
**`INTERVIEW_GUIDE`** — ei tiukka skripti, ilmapiiri: kysy tunnelma ensin, tunnista moodi, tiedä mitä EI haluta

### [2026-03-17] Tuottajaverkosto: Discogs + MusicBrainz

**Käyttötapaus:** Arppa → Väinö Karjalainen → Ursus Factory, Grandmother Corn, Karri Koira...

**`DiscogsClient.producer_graph(artist_name)`**
- Hae artisti → `artist_releases` → per release: `release_credits` → löytää extraartistit joilla role="Producer"
- Kriittinen löydös: extraartist-data on `release`-objektilla (lazy-load), ei `master`-objektilla — pitää hakea main_release masterilta ja triggeröidä täysi lataus `r.title`:llä
- Per tuottaja: `_find_producer_artists(producer_id)` käyttää tuottajan `artist_releases`:ia — Discogs listaa siellä MYÖS releaset joissa artisti on tuottajana (ei vain pääartistina). Testattu: Väinö Karjalainen id=4488400 → Ursus Factory, Karri Koira, Lyyti ym.
- `artist_releases` päivitetty palauttamaan `artist` (pääartisti) ja `role` (miten liittyy releaseen) `r.data`:sta

**`MusicBrainzClient.producer_graph(artist_name)`** — rinnakkainen toteutus MusicBrainzin kautta:
- `_recording_artist_rels(mbid)` hakee kappaleen artist-rels (tuottaja, äänittäjä jne.)
- `_productions_by_artist(mbid)` käyttää `search_recordings(arid=mbid)` — `arid` on Lucene-kenttä joka löytää kaikki kappaleet joissa MBID esiintyy missä roolissa tahansa

### [2026-03-17] keskiviikko-vol2 + API-ensimmäinen workflow + wrapper-korjaukset

**Soittolista: "keskiviikko-vol2"** (35 kpl, Spotify playlist/5lEMWBiJiSmw6bXIxkY8QP)
- Japanin musiikkiuniversumi — thematic arc: City Pop → YMO → Shibuya-kei → Jazz → Fishmans → Underground
- Ensimmäinen versio pähkäilty päästä, toinen versio API-validoitu: Last.fm similar_artists + Discogs want-arvo

**API-ensimmäinen oppiminen:**
- Ensin Last.fm `similar_artists` seeder-artisteille (Fishmans, Pizzicato Five, YMO, Ryo Fukui, Number Girl, WEG)
- Last.fm löysi: Hiroshi Suzuki, Jiro Inagaki, Shigeo Sekito, Supercar, ZAZEN BOYS, Jun Togawa, Miharu Koshi
- Discogs `release()` + want-arvo vahvisti: Hiroshi Suzuki "Cat" ⭐4.81 / 3774 want, Jiro Inagaki "Funky Stuff" ⭐4.75 / 4607 want
- 7 trackia vaihdettiin API-löydöillä — lopputulos parempi kuin pelkästä pääkopasta

**Wrapper-korjaukset (api/discogs.py):**
- `release()` community-data luki objektiattribuutteja → korjattu lukemaan `r.data['community']` dictistä
- `search_release()` lisätty `community_have` + `community_want` suoraan hakutuloksiin
- `country` parametri `search_release`:lle
- Lisätty `search_japan(query)` — oikotie country=Japan -haulle
- Rate limiter: `_throttle()` + autoretry 429 (max 3 kertaa, 5s/10s/15s viive)

**Filosofiamuutos (CLAUDE.md päivitetty):**
- API-ensimmäinen: Last.fm + Discogs → ehdotukset → Spotify URI viimeisenä
- Discogs want > 500 = merkittävä, > 2000 = klassikko
- Rate limit -tuki: kun Discogs hidastaa, täydennä Last.fm:llä ja MusicBrainzilla

## Tunnetut ongelmat / TODO

## Muistiinpanot optimointia varten
- Token-käyttö: logitetaan per API-kutsu
- Päällekkäisyydet: sama kappale useasta lähteestä → pisteytysjärjestelmä
- Signaalin vahvistus: mitä useampi lähde ehdottaa, sen parempi
