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

### [2026-03-17] Singer-songwriter lista API-validoitu + wrapper-korjaukset

**Soittolista: "Rehellisiä tarinoita"** (33 kpl, spotify:playlist:5SHZU2J4GSTjmQIIWuhT7W)
- Alkuperäinen 25 kpl lista epäiltiin omasta päästä tehdyksi → validoitiin APIlla
- Seed-artistit: Samae Koskinen + Jarkko Martikainen (Last.fm `similar_artists`)

**Validointi:**
- Last.fm `similar_artists`: Samae → Matti Johannes Koivu, Ultramariini, Liekki, Minä ja Ville Ahonen ✓
- Last.fm `similar_artists`: Jarkko → Tommi Liimatta, Herra Ylppö & Ihmiset, Dave Lindholm ✓
- Kansainväliset seedit (Ben Howard, Glen Hansard, James Vincent McMorrow jne.) → vahvistivat kaikki nykyiset kappaleet

**API-löydöt jotka puuttuivat listalta:**
- Damien Rice (want=1782, Glen Hansard similar) → "Volcano" lisätty
- Kings of Convenience (want=1081, José González similar) → "Cayman Islands"
- Iron & Wine (want=1397, City and Colour similar) → "Each Coming Night"
- The Tallest Man on Earth (want=484) → "I Won't Be Found"
- Keaton Henson (want=356, James Vincent McMorrow similar) → "You Don't Know How Lucky You Are"
- Dave Lindholm (Jarkko Martikainen similar, suomen blues-legenda) → "Pieni & hento ote"
- Topi Saha (Samae Koskinen similar) → "Se, joka karkuun pääs"
- Minä ja Ville Ahonen (Samae Koskinen similar match 0.76) → "Sano"

**Wrapper-korjaukset:**
- `api/discogs.py`: lisätty `search()` alias `search_release`:lle (lyhyempi kutsumuoto)
- `api/discogs.py`: `search_master()` saa nyt `community_have/want` kentät (aiemmin puuttui)
- `api/lastfm.py`: lisätty `artist_listeners(artist)` → kuuntelijamäärä — aiemmin ei ollut tapaa hakea tätä ilman ylimääräistä työtä
- Huomio: `similar_artists` palauttaa `SimilarArtist`-objekteja (`.name`, `.match`), ei dict:ejä — dokumentoitu `/build` skilliin

**`/build` skill päivitetty:**
- Lisätty "API-wrapperit — oikea käyttö" -osio esimerkkikoodeineen
- Selkeyttää oikeat paluumuodot per metodi (dict vs objekti), community_want-kynnykset (>2000 klassikko), sisäisen asiakkaan `sp._sp` vs väärä `sp.sp`

### [2026-03-18] api/wikipedia.py — Wikipedia & Wikidata -wrapper

**Motivaatio:** Tutkittiin mistä elokuvien soundtrackit löytyvät (TMDB ei, Tunefind maksullinen) → Wikipedia API ilmainen ja kattava.

**Wikipedia Action API:**
- `get_article(title)` — raaka wikitext
- `get_section(title, section_keyword)` — tietty osio
- `get_infobox(title)` — infobox dict:ksi parsittuna
- `get_tracklist(movie_title)` — soundtrack-tracklist, kokeilee automaattisesti `"[nimi] (soundtrack)"`, `"(film score)"` jne.
- `search(query, limit)` — artikkelien haku
- `_parse_track_listing()` — parsii `{{Track listing}}` -templaten: title/extra/length per raita, tukee useita blokkeja (levy A/B)

**Wikidata SPARQL:**
- `sparql(query)` — raaka SPARQL käytettävissä
- `oscar_winners(category, year_from, year_to)` — Best Picture / Original Score / Original Song / Director / Actor / Actress
- `artists_by_genre(genre, country)` — genre + maa -suodatus
- `film_info(film_title)` — vuosi, ohjaaja, säveltäjä, genre

**Testattu toimivaksi:**
- `get_tracklist("Seven")` → 27 kappaletta (soundtrack + score-albumit)
- `get_tracklist("Oppenheimer")` → 24 kappaletta (Ludwig Göransson)
- `oscar_winners("best_picture", 2018)` → siisti lista, vain elokuvat (ei tuottajia)
- `oscar_winners("best_original_score", 2020)` → säveltäjä per vuosi
- `oscar_winners("best_original_song", 2022)` → artistit

**Oikeat Wikidata ID:t Oscar-palkinnoille (korjattu kesken session):**
- Best Original Score: `Q488651` (ei Q106278)
- Best Original Song: `Q112243` (ei Q106746)

**Ei API-avaimia.** Rate limit: Wikipedia ~200 req/s, Wikidata SPARQL reilu.

### [2026-03-19] Soittolista "3 aamulla, Godot auki" + Discogs taustahaku

**Soittolista:** "3 aamulla, Godot auki" (30 kpl, https://open.spotify.com/playlist/1IbSicYIu67QTGguj10sWh)
- Tunnelma: uneton yö, flow-tila koodatessa / pelinkehitys, ei top-hittejä
- Genret: ambient · IDM · dream pop · chillwave · post-rock
- API-ensin: Last.fm tag-haut (ambient, chillwave, dream pop, lo-fi, IDM, late night) + similar_artists (Boards of Canada, Jon Hopkins, Tycho, Four Tet, Nils Frahm, Burial jne.)
- Discogs validoi albumien laadun: Burial Untrue want=7133, Slowdive Souvlaki want=5239, BOC want=4918
- Kaikki 30 löytyivät Spotifysta (0 ei löydettyä)
- Suunnitelmallinen syvyys: skipattu rank 1–3 per artisti, haettu rank 4–10 jotta kuuntelija löytää hitit itse

**Kappaleet (30):** Boards of Canada (Dayvan Cowboy, Music Is Math), Jon Hopkins (Lost in Thought, Abandon Window), Burial (Near Dark, Endorphin), Floating Points (Bias), Rival Consoles (Odyssey), Ólafur Arnalds (Tomorrow's Song), Grouper (Living Room), Cocteau Twins (Lorelei), Slowdive (40 Days), Bonobo (Terrapin), Emancipator (Dusk To Dawn), Ulrich Schnauss (A Letter From Home), A Winged Victory for the Sullen (All Farewells Are Sudden), Casino Versus Japan (Aquarium), Oneohtrix Point Never (Boring Angel), Helios (Halving the Compass), Hania Rani (At Dawn), Gidge (Huldra), Niklas Paschburg (Dawn), Com Truise (Propagation), Washed Out (Eyes Be Closed), Wild Nothing (Live In Dreams), The Radio Dept. (Closing Scene), Apparat (Hailin From the Edge), Tim Hecker (Boreal Kiss Pt. 1), Stars of the Lid (Don't Bother They're Here), DIIV (Past Lives)

**Discogs taustahaku — `api/discogs.py` uusi metodi:**
- `search_background(queries)` — käynnistää haut `ThreadPoolExecutor(max_workers=1)` taustasäikeessä
- Palauttaa `dict[str, Future]` heti — pääsäie voi jatkaa Last.fm/Spotify-hakuihin
- `_throttle()` tehty thread-safe (`Lock`-lukon avulla)
- Yksisäikeinen executor: rate limit hoituu luonnollisesti (ei rinnakkaisia kutsuja jotka sotketaan)
- Dokumentoitu CLAUDE.md:ään ja `/build`-skilliin oikeana käyttötapana

**Muuttuneet tiedostot:** `api/discogs.py` (search_background + Lock + thread-safe throttle), `CLAUDE.md` (Discogs taustahaku -ohje koodiesimerkin kanssa), `.claude/commands/build.md` (Discogs-osio päivitetty oikeaan käyttötapaan)

## Tunnetut ongelmat / TODO

## Muistiinpanot optimointia varten
- Token-käyttö: logitetaan per API-kutsu
- Päällekkäisyydet: sama kappale useasta lähteestä → pisteytysjärjestelmä
- Signaalin vahvistus: mitä useampi lähde ehdottaa, sen parempi
