#!/usr/bin/env python3
"""
Spotify-autentikointi.

Aja kerran alussa (tai kun token on vanhentunut):
    python scripts/auth.py

Flow:
  1. Selain aukeaa Spotify-kirjautumissivulle
  2. Kirjaudut ja hyväksyt
  3. Spotify redirectaa http://127.0.0.1:8000/auth/callback
  4. Tämä skripti nappaa callbackin, tallentaa tokenin
  5. Tulostaa käyttäjäsi tiedot — valmis

Jatkossa SpotifyClient refreshaa tokenin automaattisesti.
Token tallennetaan: .spotify_token_cache
"""

import os
import sys

from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from api.spotify import SCOPES

load_dotenv()


def main() -> None:
    cache = ".spotify_token_cache"

    auth = SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8000/auth/callback"),
        scope=SCOPES,
        cache_path=cache,
        open_browser=True,
    )

    # Onko cachessa voimassa oleva token?
    token_info = auth.get_cached_token()
    if token_info and not auth.is_token_expired(token_info):
        print("✓ Token löytyi cachesta, ei tarvetta kirjautua uudelleen.")
    else:
        if token_info and auth.is_token_expired(token_info):
            print("↻ Token vanhentunut — refreshataan...")
            token_info = auth.refresh_access_token(token_info["refresh_token"])
            if token_info:
                print("✓ Token refreshattu.")
        else:
            print("→ Ei tokenia — avataan selain kirjautumista varten...")
            print(f"  Redirect URI: {os.getenv('SPOTIFY_REDIRECT_URI')}")
            print("  (Varmista että tämä on lisätty Spotify Developer Dashboard:iin)\n")

    sp = spotipy.Spotify(auth_manager=auth)

    try:
        user = sp.current_user()
        print(f"\n Kirjauduttu Spotifyyn:")
        print(f"  Nimi:    {user.get('display_name', '?')}")
        print(f"  ID:      {user['id']}")
        print(f"  Email:   {user.get('email', '?')}")
        print(f"  Maa:     {user.get('country', '?')}")
        print(f"\n  Token cachessa: {cache}")
    except spotipy.SpotifyException as e:
        print(f"\n✗ Virhe: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
