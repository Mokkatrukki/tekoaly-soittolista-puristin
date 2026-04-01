# Soittolista-puristin

Claude Code -työkalu joka toimii musiikkikuraattorina. Kerrot mitä soittolistaa haluat,
Claude kyselee tarkentavia kysymyksiä, hakee dataa useista musiikki-APIeista ja rakentaa
soittolistan Spotifyyn.

Ei käyttöliittymää — ajatellaan ääneen Claude Coden kanssa ja katsotaan mitä syntyy.

## Vaatimukset

- Python 3.12+
- API-avaimet (ks. alla)

## API-avaimet

Kopioi `.env.example` → `.env` ja täytä avaimet:

| Palvelu | Rekisteröinti | Pakollinen |
|---------|--------------|------------|
| Spotify | [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) | ✓ |
| Last.fm | [last.fm/api/account/create](https://www.last.fm/api/account/create) | ✓ |
| Discogs | [discogs.com/settings/developers](https://www.discogs.com/settings/developers) | ✓ |
| ListenBrainz | [listenbrainz.org/settings](https://listenbrainz.org/settings/) | |
| MusicBrainz | — ei tarvita | |
| Wikipedia | — ei tarvita | |

Spotify-appissa aseta Redirect URI: `http://127.0.0.1:8000/auth/callback`

## Asennus

```bash
git clone git@github.com:mokkatrukki/tekoaly-soittolista-puristin.git
cd tekoaly-soittolista-puristin

python -m venv .venv
source .venv/bin/activate
pip install -e .

cp .env.example .env
# täytä .env-tiedosto
```

## Spotify-autentikaatio

Ensimmäisellä käynnistyksellä Spotify vaatii OAuth-hyväksynnän selaimessa:

```bash
python -m scripts.auth
```

## Käyttö

Avaa Claude Code projektin juuressa ja kerro mitä soittolistaa haluat.
Claude käyttää APIeja suoraan ja rakentaa soittolistan Spotifyyn.

Valmis soittolista-tiedosto ajetaan näin:

```bash
python -m scripts.build_playlist playlists/oma_soittolista.py
python -m scripts.build_playlist playlists/oma_soittolista.py --skip-bad   # ohita epävarmat osumat
python -m scripts.build_playlist playlists/oma_soittolista.py --no-confirm  # ilman vahvistusta
```

Soittolista-tiedosto on yksinkertainen Python-tiedosto:

```python
NAME = "Soittolistan nimi"
DESCRIPTION = "Kuvaus"
TRACKS = [
    ("Artisti", "Kappale"),
    ...
]
```

## Rajoitukset

Spotify Development mode estää useita endpointteja:

- `/recommendations` — poistettu pysyvästi
- `/audio-features`, `/artists/{id}/related-artists` — estetty
- Discovery tapahtuu Last.fm + Discogs + MusicBrainz kautta

## Lisenssi

MIT
