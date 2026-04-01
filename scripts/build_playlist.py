#!/usr/bin/env python3
"""
Soittolistan rakentaja.

Käyttö:
    python -m scripts.build_playlist playlists/keskiviikko_motorik_kosmos.py
    python -m scripts.build_playlist playlists/jokin_toinen.py --skip-bad
    python -m scripts.build_playlist playlists/jokin.py --no-confirm

Playlist-tiedosto määrittelee kolme muuttujaa:
    NAME        = "Soittolistan nimi"
    DESCRIPTION = "Kuvaus"
    TRACKS      = [("Artisti", "Kappale"), ...]
"""

import sys
import re
import importlib.util
import argparse
from pathlib import Path

sys.path.insert(0, ".")
from api.spotify import SpotifyClient


def _normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _match_quality(query_artist: str, query_title: str, result) -> str:
    ra = _normalize(result.artist)
    rt = _normalize(result.name)
    qa = _normalize(query_artist)
    qt = _normalize(query_title)
    artist_ok = qa[:5] in ra or ra[:5] in qa
    title_ok = qt[:6] in rt or rt[:6] in qt
    if artist_ok and title_ok:
        return "✓"
    elif artist_ok or title_ok:
        return "?"
    return "✗"


def load_playlist_file(path: str) -> tuple[str, str, list]:
    p = Path(path)
    if not p.exists():
        print(f"Virhe: tiedostoa ei löydy: {path}")
        sys.exit(1)
    spec = importlib.util.spec_from_file_location("playlist_data", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    name = getattr(mod, "NAME", p.stem)
    desc = getattr(mod, "DESCRIPTION", "")
    tracks = getattr(mod, "TRACKS", [])
    return name, desc, tracks


def search_tracks(sp: SpotifyClient, tracks: list[tuple[str, str]]) -> list[dict]:
    results = []
    for query_artist, query_title in tracks:
        q = f"artist:{query_artist} track:{query_title}"
        hits = sp.search_tracks(q, limit=1)
        if hits:
            t = hits[0]
            results.append({
                "status": _match_quality(query_artist, query_title, t),
                "uri": t.uri,
                "artist": t.artist,
                "name": t.name,
                "query_artist": query_artist,
                "query_title": query_title,
            })
        else:
            results.append({
                "status": "✗",
                "uri": None,
                "artist": None,
                "name": None,
                "query_artist": query_artist,
                "query_title": query_title,
            })
    return results


def print_results(results: list[dict]) -> None:
    found = sum(1 for r in results if r["uri"])
    uncertain = [r for r in results if r["status"] in ("?", "✗")]
    print(f"\nLöytyi: {found}/{len(results)}\n")
    for r in results:
        if r["uri"]:
            print(f"  {r['status']}  {r['query_artist']} — {r['query_title']}")
            if r["status"] != "✓":
                print(f"       → {r['artist']} — {r['name']}")
        else:
            print(f"  ✗  {r['query_artist']} — {r['query_title']}  [EI LÖYDY]")
    if uncertain:
        print(f"\n⚠  {len(uncertain)} epävarma osuma — tarkista ennen jatkamista")


def build_playlist(
    name: str,
    description: str,
    tracks: list[tuple[str, str]],
    skip_bad: bool = False,
    confirm: bool = True,
) -> str | None:
    sp = SpotifyClient()

    print(f"Haetaan {len(tracks)} kappaletta...")
    results = search_tracks(sp, tracks)
    print_results(results)

    if skip_bad:
        good = [r for r in results if r["uri"] and r["status"] == "✓"]
        skipped = [r for r in results if r["uri"] and r["status"] == "?"]
        if skipped:
            print(f"\n--skip-bad: jätetään pois {len(skipped)} ?-osumaa")
    else:
        good = [r for r in results if r["uri"]]

    missing = [r for r in results if not r["uri"]]
    if missing:
        print(f"\nPuuttuvat ({len(missing)} kpl):")
        for r in missing:
            print(f"  {r['query_artist']} — {r['query_title']}")

    print(f"\nSoittolista: '{name}'")
    print(f"Lisätään: {len(good)} kappaletta")

    if confirm:
        try:
            ans = input("\nJatketaan? [y/N] ").strip().lower()
        except EOFError:
            ans = ""
        if ans != "y":
            print("Peruutettu.")
            return None

    playlist = sp.create_playlist(name=name, description=description, public=False)
    sp.add_tracks(playlist["id"], [r["uri"] for r in good])

    url = playlist["url"]
    print(f"\n✓ Valmis! {len(good)} kappaletta")
    print(f"  {url}")
    return url


def main():
    parser = argparse.ArgumentParser(description="Rakenna Spotify-soittolista tiedostosta")
    parser.add_argument("playlist_file", help="Polku playlist-tiedostoon (esim. playlists/foo.py)")
    parser.add_argument("--skip-bad", action="store_true", help="Jätä ?-osumat pois")
    parser.add_argument("--no-confirm", action="store_true", help="Luo lista ilman vahvistusta")
    args = parser.parse_args()

    name, desc, tracks = load_playlist_file(args.playlist_file)
    build_playlist(
        name=name,
        description=desc,
        tracks=tracks,
        skip_bad=args.skip_bad,
        confirm=not args.no_confirm,
    )


if __name__ == "__main__":
    main()
