"""
Uuden musiikin löytäjä — 50 nousevaa kappaletta.

Lähteet:
  1. ListenBrainz Fresh Releases (30 pv, listen_count-järjestys)
     → trending uudet julkaisut globaalisti
  2. Spotify new_releases(FI) → tuoreet albumit Suomen markkinalla
  3. Last.fm tag-haku: "suomi", "suomipop", "finnish" → suomalaisia artisteja

Strategia:
  - LB fresh releases → 1 kappale per albumi (ensimmäinen/suosituin)
  - Spotify FI new releases → 1 kappale per albumi (ensimmäinen kappale)
  - Last.fm suomalaiset artistit → etsi heidän uusimmat kappaleet LB:stä
  - Pisteytysjärjestelmä: useampi lähde = korkeampi piste
  - Suomi-boosti: +1 piste suomalaisille
  - Deduplikaatio, 50 parhaan valinta
  - Spotify-soittolistan luonti

Käyttö:
  python -m scripts.discover_new
  python -m scripts.discover_new --no-playlist   # vain näyttö, ei luo
  python -m scripts.discover_new --days 14       # 14 pv ikkuna
"""

import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from api.listenbrainz import ListenBrainzClient
from api.spotify import SpotifyClient
from api.lastfm import LastFmClient

console = Console()

FINNISH_TAGS = ["suomi", "suomipop", "suomihiphop", "suomirock", "suomijazz", "finland", "finnish"]


# ─── Hakufunktiot ────────────────────────────────────────────────────────────

def fetch_lb_releases(days: int = 30) -> list[dict]:
    """LB Fresh Releases — palauttaa albumit [{artist, album, release_date, tags}]"""
    lb = ListenBrainzClient()
    releases = lb.fresh_releases(days=days, sort="listen_count", limit=150)
    console.print(f"   [dim]LB: {len(releases)} tuoretta julkaisua löytyi[/dim]")
    return releases


def fetch_spotify_fi_albums(sp: SpotifyClient) -> list[dict]:
    """Spotify FI new releases — palauttaa albumit [{album_id, album_name, artist, release_date}]"""
    try:
        albums = sp.new_releases(country="FI", limit=50)
        console.print(f"   [dim]Spotify FI: {len(albums)} uutta albumia[/dim]")
        return albums
    except Exception as e:
        console.print(f"   [yellow]Spotify new_releases epäonnistui: {e}[/yellow]")
        return []


def fetch_finnish_artists_lastfm(lfm: LastFmClient, limit_per_tag: int = 20) -> set[str]:
    """Kerää suomalaisia artisteja Last.fm-tagien kautta."""
    artists: set[str] = set()
    for tag in FINNISH_TAGS:
        try:
            results = lfm.tag_top_artists(tag, limit=limit_per_tag)
            for r in results:
                artists.add(r["name"].lower())
        except Exception:
            pass
    console.print(f"   [dim]Last.fm: {len(artists)} suomalaista artistia tagien kautta[/dim]")
    return artists


# ─── Pisteytysjärjestelmä ────────────────────────────────────────────────────

class Candidate:
    """Potentiaalinen kappale pisteineen."""
    def __init__(self, artist: str, title: str, album: str = ""):
        self.artist = artist
        self.title = title
        self.album = album
        self.score = 0.0
        self.sources: list[str] = []
        self.is_finnish = False
        self.release_date = ""
        self.spotify_uri: str | None = None
        self.spotify_id: str | None = None

    @property
    def key(self) -> str:
        return f"{self.artist.lower()}::{self.title.lower()}"

    def add_source(self, source: str, points: float = 1.0):
        if source not in self.sources:
            self.sources.append(source)
        self.score += points

    def __str__(self):
        flags = ""
        if self.is_finnish:
            flags += " 🇫🇮"
        sources_str = "+".join(self.sources)
        return f"{self.artist} — {self.title}{flags}  [{sources_str}, {self.score:.1f}p]"


# ─── Päälogiikka ─────────────────────────────────────────────────────────────

def build_candidates(
    lb_releases: list[dict],
    sp_albums: list[dict],
    finnish_artists: set[str],
    sp: SpotifyClient,
) -> dict[str, Candidate]:
    candidates: dict[str, Candidate] = {}

    # --- LB Fresh Releases ---
    console.print("\n[cyan]Rakennetaan ehdokkaat LB:stä...[/cyan]")
    lb_added = 0
    for release in lb_releases:
        artist = release["artist"]
        album = release["album"]
        if not artist or not album:
            continue

        # Hae ensimmäinen kappale Spotifysta
        query = f"album:{album} artist:{artist}"
        try:
            tracks = sp.search_tracks(query, limit=3, market="FI")
        except Exception:
            tracks = []

        if not tracks:
            # Fallback: hae artistin nimellä + albumin ensimmäinen sana
            try:
                tracks = sp.search_tracks(f"{artist} {album.split()[0]}", limit=3, market="FI")
            except Exception:
                tracks = []

        if not tracks:
            continue

        t = tracks[0]
        key = f"{t.artist.lower()}::{t.name.lower()}"
        if key not in candidates:
            c = Candidate(t.artist, t.name, album)
            c.release_date = release.get("release_date", "")
            candidates[key] = c
        candidates[key].add_source("LB", 1.0)
        candidates[key].spotify_uri = t.uri
        candidates[key].spotify_id = t.id

        if artist.lower() in finnish_artists:
            candidates[key].is_finnish = True
            candidates[key].add_source("FI", 0.5)

        lb_added += 1
        if lb_added >= 80:
            break

    console.print(f"   [dim]LB-ehdokkaita: {lb_added} (Spotify-haku onnistui)[/dim]")

    # --- Spotify FI new releases ---
    console.print("[cyan]Rakennetaan ehdokkaat Spotify FI:stä...[/cyan]")
    sp_added = 0
    for album in sp_albums[:30]:
        album_id = album["album_id"]
        try:
            tracks = sp.album_tracks(album_id, market="FI")
        except Exception:
            continue
        if not tracks:
            continue

        t = tracks[0]  # Ensimmäinen kappale albumilta
        key = f"{t.artist.lower()}::{t.name.lower()}"
        if key not in candidates:
            c = Candidate(t.artist, t.name, album["album_name"])
            c.release_date = album.get("release_date", "")
            candidates[key] = c
        candidates[key].add_source("Spotify-FI", 1.0)
        candidates[key].spotify_uri = t.uri
        candidates[key].spotify_id = t.id

        if t.artist.lower() in finnish_artists:
            candidates[key].is_finnish = True
            candidates[key].add_source("FI", 0.5)

        sp_added += 1
        time.sleep(0.05)  # kevyt rate limit

    console.print(f"   [dim]Spotify FI -ehdokkaita: {sp_added}[/dim]")

    return candidates


def select_top(
    candidates: dict[str, Candidate],
    target: int = 50,
    min_finnish: int = 10,
) -> list[Candidate]:
    """
    Valitse 50 parasta ehdokasta.
    Varmistetaan vähintään 10 suomalaista.
    Max 2 kappaletta per artisti variaation vuoksi.
    """
    all_c = list(candidates.values())
    all_c.sort(key=lambda c: (c.score, c.release_date), reverse=True)

    finnish = [c for c in all_c if c.is_finnish]
    non_finnish = [c for c in all_c if not c.is_finnish]

    selected: list[Candidate] = []
    artist_count: dict[str, int] = defaultdict(int)

    def try_add(c: Candidate) -> bool:
        if artist_count[c.artist.lower()] >= 2:
            return False
        selected.append(c)
        artist_count[c.artist.lower()] += 1
        return True

    # Ensin suomalaiset (vähintään min_finnish)
    fi_added = 0
    for c in finnish:
        if fi_added >= min_finnish:
            break
        if try_add(c):
            fi_added += 1

    # Sitten täytetään loput
    for c in all_c:
        if len(selected) >= target:
            break
        if c not in selected:
            try_add(c)

    return selected[:target]


# ─── Näyttö ──────────────────────────────────────────────────────────────────

def show_table(tracks: list[Candidate]):
    table = Table(title=f"Uutta musiikkia — {len(tracks)} kappaletta", show_lines=False)
    table.add_column("#", style="dim", width=3)
    table.add_column("Artisti", style="bold", min_width=20)
    table.add_column("Kappale", min_width=25)
    table.add_column("Albumi", style="dim", min_width=15)
    table.add_column("Pvm", style="dim", width=11)
    table.add_column("Lähteet", style="cyan", width=18)

    for i, t in enumerate(tracks, 1):
        fi_flag = " 🇫🇮" if t.is_finnish else ""
        table.add_row(
            str(i),
            f"{t.artist}{fi_flag}",
            t.title,
            t.album[:20] + ("…" if len(t.album) > 20 else ""),
            t.release_date[:10],
            "+".join(t.sources),
        )
    console.print(table)


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Etsi 50 uutta/nousevaa kappaletta")
    parser.add_argument("--days", type=int, default=30, help="Kuinka monta päivää taaksepäin (oletus 30)")
    parser.add_argument("--no-playlist", action="store_true", help="Älä luo Spotify-soittolistaa")
    parser.add_argument("--min-finnish", type=int, default=10, help="Vähintään N suomalaista kappaletta")
    args = parser.parse_args()

    console.rule("[bold green]Uuden musiikin etsintä[/bold green]")
    console.print(f"Ajanjakso: viimeiset [bold]{args.days}[/bold] päivää | Kohde: 50 kappaletta\n")

    # 1. Hae data
    console.print("[bold]1. Haetaan uudet julkaisut...[/bold]")
    lb_releases = fetch_lb_releases(days=args.days)

    sp = SpotifyClient()
    sp_albums = fetch_spotify_fi_albums(sp)

    lfm = LastFmClient()
    finnish_artists = fetch_finnish_artists_lastfm(lfm, limit_per_tag=30)

    # 2. Rakenna ehdokkaat
    console.print("\n[bold]2. Rakennetaan ehdokaslista...[/bold]")
    candidates = build_candidates(lb_releases, sp_albums, finnish_artists, sp)
    console.print(f"   [green]Yhteensä {len(candidates)} uniikkia ehdokasta[/green]")

    # 3. Valitse top 50
    top50 = select_top(candidates, target=50, min_finnish=args.min_finnish)
    fi_count = sum(1 for t in top50 if t.is_finnish)
    console.print(f"   [green]Valittu: {len(top50)} kappaletta ({fi_count} suomalaista)[/green]")

    # 4. Näytä taulukko
    console.print()
    show_table(top50)

    # 5. Luo Spotify-soittolista
    uris = [t.spotify_uri for t in top50 if t.spotify_uri]
    if not uris:
        console.print("\n[red]Ei Spotify URI:eja — soittolistaa ei luoda.[/red]")
        return

    if args.no_playlist:
        console.print(f"\n[dim]--no-playlist: {len(uris)} kappaletta löytyi mutta soittolistaa ei luoda.[/dim]")
        return

    from datetime import date
    playlist_name = f"Uutta nousevaa — {date.today().strftime('%B %Y')}"
    console.print(f"\n[bold]3. Luodaan soittolista: [green]{playlist_name}[/green]...[/bold]")

    try:
        fi_artists = [t.artist for t in top50 if t.is_finnish][:3]
        fi_str = ", ".join(fi_artists) + " ym." if fi_artists else "globaali löytö"
        desc = (
            f"50 uutta nousevaa kappaletta, löydetty {date.today().strftime('%d.%m.%Y')}. "
            f"Suomalaiset: {fi_str}. Lähteet: ListenBrainz, Spotify FI."
        )
        playlist = sp.create_playlist(playlist_name, description=desc, public=True)
        sp.add_tracks(playlist["id"], uris)

        console.print(f"[bold green]✓ Soittolista luotu![/bold green]")
        console.print(f"  Nimi: {playlist_name}")
        console.print(f"  Kappaleet: {len(uris)}")
        console.print(f"  URL: {playlist.get('url', 'N/A')}")
    except Exception as e:
        console.print(f"[red]Soittolistan luonti epäonnistui: {e}[/red]")

    console.print()
    console.print("[dim]API-kutsut:[/dim]")
    summary = sp.log_summary()
    console.print(f"[dim]  Spotify: {summary['total_calls']} kutsua, {summary['total_latency_ms']:.0f}ms[/dim]")


if __name__ == "__main__":
    main()
