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
│   └── playlist_builder.py      # Kokoaa soittolistan API-datojen pohjalta
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

- `GET /recommendations` — **DEPRECATED** mutta toimii edelleen, käytetään
- `GET /audio-features/{id}` — toimii normaalisti
- Vanhat playlist-endpointit deprecated — käytetään uusia (`add-items-to-playlist`)
- `preview_url`, `popularity`, `available_markets` responseissa deprecated
- Spotify-sisältöä **ei saa käyttää** ML/AI-mallien kouluttamiseen (lisenssi)

## Git

- Käyttäjä: `mokkatrukki@gmail.com`
- SSH-avain: `~/.ssh/id_ed25519_mokkatrukki` via host `github-mokkatrukki`
- Remote-URL muoto: `git@github-mokkatrukki:mokkatrukki/repo.git`
- **Push on käyttäjän vastuulla** — Claude ei pushaa

## Kehitysperiaatteet

### Logiikka soittolistan rakentamisessa
1. **Haastattelu** — kysy käyttäjältä: tunnelma, tilanne, referenssikappaleita, mitä EI haluta
2. **Monilähteinen haku** — sama artisti/genre useasta lähteestä vahvistaa signaalia
3. **Pisteytysjärjestelmä** — kappale saa pisteitä jokaisesta lähteestä joka sen ehdottaa
4. **Deduplikaatio** — sama kappale eri lähteistä = 1 kappale korkeammalla pisteellä
5. **Spotify-kirjasto** — tarkistetaan löytyykö kappale, haetaan URI, lisätään listaan

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
