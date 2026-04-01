# Soittolista-puristin — CLAUDE.md

## Mitä tämä on

Claude Code -härveli joka toimii musiikkikuraattorina. Käyttäjä kertoo mitä soittolistaa haluaa,
Claude kyselee tarkentavia kysymyksiä ja hakee dataa useista rajapinnoista, sitten rakentaa
soittolistan Spotifyyn.

**Ei MCP** — Claude käyttää rajapintoja suoraan Python-koodilla session aikana.

## Rajapinnat

| API | Kirjasto | Käyttötarkoitus |
|-----|----------|-----------------|
| Spotify | `spotipy` | Haku, soittolistan luonti, audio features, recommendations (deprecated mutta toimii) |
| Last.fm | `pylast` | Samankaltaiset kappaleet/artistit, tagit, kuuntelijadata |
| Discogs | `discogs_client` | Genret, julkaisuvuodet, harvinaiset löydöt, laatu-indikaattorit |
| MusicBrainz | `musicbrainzngs` | Metatiedot, suhteet artistien välillä (ei API-avainta tarvita) |
| ListenBrainz | `liblistenbrainz` | Kuunteludata, samankaltaissuositukset |
| YLE Areena | httpx suoraan | Musiikkiohjelmien kuvaukset → soittolistat |
| Wikipedia | httpx suoraan | Genren historia, infobox, `get_genre_info()` — käytä genren kartoitukseen |
| Wikidata | SPARQL | Artistit genren/maan mukaan, elokuvatiedot — `artists_by_genre()` |

## API-avaimet (.env)

```
SPOTIFY_CLIENT_ID=333f50f1010948fab375856280b49ad0
SPOTIFY_CLIENT_SECRET=b547e35cc32f49c99e4fc1772696dda8
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/auth/callback
LASTFM_API_KEY=a594a0c3acdb6150e1904da7b5611221
DISCOGS_TOKEN=vvUidrAMLifkRknzuZJKkbhZWKTXAEOnLiUnpQqG
LB_TOKEN=e3b0daaf-04b7-4c6a-8a4b-359de392f8ca
```
MusicBrainz: ei avainta tarvita, User-Agent pitää asettaa.

## Projektirakenne

```
tekoäly-soittolista-puristin/
├── .env                          # API-avaimet (gitignore)
├── pyproject.toml                # Python-riippuvuudet
├── CLAUDE.md                     # Tämä tiedosto
├── LETSBUILD.md                  # Build log — mitä on tehty ja miksi
│
├── tools/
│   ├── fetch_doc.py              # Hakee API-doku URL:sta tai nimetystä avaimesta
│   └── distill.py                # Kohinanpoistaja — token-optimointi
│
├── api/
│   ├── sources.py                # Nimetyt doc-URL:t: fetch_doc("spotify.search")
│   ├── spotify.py                # Spotify-wrapper (spotipy)
│   ├── lastfm.py                 # Last.fm-wrapper (pylast)
│   ├── discogs.py                # Discogs-wrapper
│   ├── musicbrainz.py            # MusicBrainz-wrapper
│   ├── listenbrainz.py           # ListenBrainz-wrapper
│   └── yle_areena.py             # YLE Areena -scraper
│
├── curator/
│   ├── interviewer.py            # Vuoropuhelun logiikka käyttäjän kanssa
│   ├── playlist_builder.py      # Kokoaa soittolistan API-datojen pohjalta
│   └── philosophies/
│       ├── INDEX.md             # Filosofioiden hakemisto
│       └── symphonic_poem.md   # Ensimmäinen filosofia — pylväät/kansi/valot
│
├── playlists/                    # Valmiit soittolistat (.py-tiedostoja)
│
└── logs/
    └── sessions/                 # JSON-logit sessioittain (gitignore)
```

## Työkalut

### fetch_doc — API-dokumentaation haku

```bash
# Listaa kaikki avaimet
python -m tools.fetch_doc --list
python -m tools.fetch_doc --list spotify

# Hae dokumentaatio
python -m tools.fetch_doc spotify.search          # ~3800 tokenia, täysi doku
python -m tools.fetch_doc spotify.search --aggressive  # ~180 tokenia, vain struktuuri
python -m tools.fetch_doc spotify.search --raw    # raaka, ei kohinanpoistoa
python -m tools.fetch_doc spotify.search --yaml   # YAML-muoto
```

Koodissa:
```python
from tools.fetch_doc import fetch_doc
doc = fetch_doc("spotify.search")
doc_tiivistetty = fetch_doc("spotify.search", aggressive=True)
```

### distill — kohinanpoisto erikseen

```python
from tools.distill import distill, token_estimate
puhdas = distill(raaka_teksti, aggressive=True)
print(token_estimate(puhdas))
```

## Tärkeät huomiot Spotify-rajapinnasta

**⚠️ Spotify blokkaa Discovery-endpointit Development mode -applikaatioilta (testattu 2026-03-17):**
- ❌ `/recommendations` — poistettu (404) — käytä Last.fm/ListenBrainz
- ❌ `/browse/new-releases` — estetty (403) — käytä ListenBrainz fresh_releases
- ❌ `/artists/{id}/related-artists` — estetty (403)
- ❌ `/artists/{id}/top-tracks` — estetty (403)
- ❌ `/audio-features` — estetty (403)
- ❌ `/recommendations/available-genre-seeds` — poistettu (404)

**✅ Toimii Development modessa:**
- `search` (tracks + artists) — käytetään kappaleiden löytämiseen nimellä
- `recently_played`, `top_tracks`, `top_artists` — käyttäjän kuunteludata personalisointiin
- Soittolistan hallinta: `create_playlist`, `add_tracks`, `remove_tracks`, `get_playlist`, `user_playlists`

**Arkkitehtuurivaikutus:**
- Spotify = kohde (soittolista luodaan sinne) + personalisointilähde (mitä käyttäjä on kuunnellut)
- Discovery = Last.fm `track.getSimilar` + `artist.getSimilar`, ListenBrainz, MusicBrainz
- Spotify `search` käytetään vain löydettyjen kappaleiden URI:n hakemiseen

- Spotify-sisältöä **ei saa käyttää** ML/AI-mallien kouluttamiseen (lisenssi)

## Git

- Käyttäjä: `mokkatrukki@gmail.com`
- SSH-avain: `~/.ssh/id_ed25519_mokkatrukki` via host `github-mokkatrukki`
- Remote-URL muoto: `git@github-mokkatrukki:mokkatrukki/repo.git`
- **Push on käyttäjän vastuulla** — Claude ei pushaa

## API-kutsujen ajaminen session aikana

**Ei väliaikaisia .py-tiedostoja.** Tutkimus- ja rakennuskoodi ajetaan suoraan bashilla:

```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from api.lastfm import LastFmClient
lfm = LastFmClient()
for a in lfm.similar_artists('Pixel Grip', limit=20):
    print(a)
"
```

Ainoa pysyvä `.py`-tiedosto on valmis soittolista `playlists/nimi.py`.
Tutkimus, URI-haku ja soittolistan luonti tapahtuvat bash-komennoilla sessoin aikana.

## Kehitysperiaatteet

### API-ensimmäinen filosofia (TÄRKEÄÄ)
**APIen data on totuus. Oma tietämys maustaa, ei johda.**

1. **Älä keksi päässä** — ei artisti- tai kappalelistan pähkäilyä ilman API-vahvistusta
2. **Laaja haku ensin** — Last.fm `similar_artists`, Discogs `search_japan`, MusicBrainz tagit
3. **Discogs vahvistaa laadun** — `community.want` = keräilyarvo = laatu-indikaattori
4. **Last.fm vahvistaa suosion** — `playcount`, `listeners`, `artist_tags` kertovat tagit
5. **Spotify viimeisenä** — vain URI:n löytämiseen, ei discovery-lähteenä

### Logiikka soittolistan rakentamisessa

**Ensin lue `curator/philosophies/INDEX.md`** — valitse filosofia ennen kuin aloitat.
Filosofia määrää rakenteen, artisti-hajontasäännöt ja rakennuskysymykset.

1. **Haastattelu** — kysy käyttäjältä: tunnelma, tilanne, referenssikappaleita, mitä EI haluta
2. **Tarkista kuunteluhistoria** — `sp.recently_played()` → vältä viimeisen 30pv kappaleet
3. **Laaja API-haku** — Last.fm `similar_artists` + `tag_top_tracks`, Discogs `search_japan`
4. **Laadun suodatus** — Discogs want-arvo > 500 = merkittävä, > 2000 = klassikko
5. **Monilähteinen vahvistus** — sama artisti useasta API:sta = vahva signaali
6. **Pisteytysjärjestelmä** — kappale saa pisteitä jokaisesta lähteestä joka sen ehdottaa
7. **Deduplikaatio** — sama kappale eri lähteistä = 1 kappale korkeammalla pisteellä
8. **Spotify viimeisenä** — tarkistetaan löytyykö kappale, haetaan URI

### Last.fm similar — korkea vs. matala match

`track.getSimilar` palauttaa tuloksia match-arvolla 0–1:

- **Korkea match (>0.5)** = pysyy genressä, turvalliset siirtymät, kannen täyte
- **Matala match (<0.3)** = genrerajat alkavat hämärtyä — sieltä löytyvät **pakotiet**
  ja yllätykset jotka tuntuvat silti oikeilta. Etsi tästä alueesta valot ja temaattiset sillat.

Jos sama artisti nousee matalan matchin alueelta useasta eri lähtökappaleesta →
vahva signaali: se artisti resonoi teeman tasolla, ei genren tasolla.

### Artistihajonta soittolistassa

Lue aktiivisen filosofian hajontasäännöt. Periaatteet `symphonic_poem`-filosofiassa:
- Sama artisti: vähintään 6–8 kappaletta välissä
- Sama albumi: max 1 kappale
- Poikkeukset ovat mahdollisia — mutta niiden pitää olla tietoisia valintoja, ei laiskuutta

### API-rajoitukset ja tukeminen
- **Discogs**: 60 req/min (token). Wrapper hoitaa rate limitin (1.1s/kutsu, autoretry 429)
  - **⚠️ HIDAS — käytä `search_background()` niin se ei blokkaa muuta hakua!**
  - Oikea tapa: käynnistä Discogs taustalle → tee Last.fm-haut → nouda Discogs-tulokset vasta lopussa

```python
# ✅ OIKEIN — Discogs taustalla, ei blokkaa
futures = dc.search_background([
    ('Burial Untrue', 3),
    ('Jon Hopkins Immunity', 2),
    ('Boards of Canada Music Has the Right to Children', 2),
])
# Tee Last.fm-haut tässä välissä (Discogs pyörii taustalla)
similar = lfm.similar_artists('Burial', limit=20)
tag_tracks = lfm.tag_top_tracks('ambient', limit=20)
# Nouda Discogs-tulokset vasta kun tarvitaan
for query, fut in futures.items():
    results = fut.result()  # blokkaa vain jos ei vielä valmis
    for r in results:
        print(r['title'], r['community_want'])

# ❌ VÄÄRIN — jokainen haku blokkaa 1.2s
for album in albums:
    results = dc.search(album, limit=2)  # odottaa 1.2s per kutsu
```
- **Last.fm**: ~5 req/s, ei ongelmia. Käytä tag-hakuja löytämiseen, similar_artists graphiin
- **MusicBrainz**: ei API-avainta, mutta hidas. Käytä artistisuhteiden selvittämiseen
- **Spotify**: Discovery-endpointit estetty (ks. yllä). Vain search + playlist management

### Logitus (logs/sessions/)
Jokainen sessio lokataan JSON:iin:
- Käyttäjän kuvaus soittolistasta
- Per API-kutsu: endpoint, parametrit, vastauksen koko, latenssi
- Ehdotetut kappaleet per lähde
- Lopullinen lista + pisteet
- Token-käyttö arvio

### Token-optimointi
- `fetch_doc(..., aggressive=True)` kun tarvitaan vain nopea tarkistus
- Logit kertovat mitkä API-kutsut tuottavat päällekkäistä dataa
- Tavoite: vähentää redundantteja hakuja ajan myötä

## /checkpoint

Käytä kun looginen kokonaisuus on valmis:
1. Päivitä `LETSBUILD.md` → Valmiit osat
2. `git add` relevantit tiedostot (ei .env)
3. `git commit -m "feat/fix: kuvaus"` — **ei** Co-Authored-By -riviä
4. Muistuta käyttäjää pushista

## Virtual environment

```bash
source .venv/bin/activate
# tai
.venv/bin/python -m tools.fetch_doc spotify.search
```
