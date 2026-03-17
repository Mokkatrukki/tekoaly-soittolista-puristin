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

## Tunnetut ongelmat / TODO

## Muistiinpanot optimointia varten
- Token-käyttö: logitetaan per API-kutsu
- Päällekkäisyydet: sama kappale useasta lähteestä → pisteytysjärjestelmä
- Signaalin vahvistus: mitä useampi lähde ehdottaa, sen parempi
