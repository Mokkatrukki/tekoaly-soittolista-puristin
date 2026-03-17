"""
PlaylistBuilder — kokoaa soittolistan useista lähteistä.

Käyttö:
    builder = PlaylistBuilder()
    builder.add(lastfm_tracks, source="lastfm", weight=1.0)
    builder.add(chart_tracks, source="charts", weight=1.5)
    builder.add(areena_tracks, source="areena", weight=1.2)

    ranked = builder.rank(limit=25)          # deduploi ja pisteytetty lista
    uris = builder.resolve(spotify, ranked)  # hae Spotify-URI:t
    playlist_url = builder.create(spotify, "Nimi", uris)

Pisteytys:
    - Jokainen lähde lisää painotetun pisteen kandidaatille
    - Sama kappale useasta lähteestä → pisteet summataan (signaali vahvistuu)
    - Normalisointi: lähteen ensimmäinen kappale saa täydet pisteet,
      viimeinen saa 1/n (lineaarinen lasku)

Logitus:
    builder.session → dict jossa kaikki mitä tehtiin (JSON-serialisoituva)
"""

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


# ─── Dataluokat ──────────────────────────────────────────────────────────────

@dataclass
class Candidate:
    artist: str
    title: str
    score: float = 0.0
    sources: list[str] = field(default_factory=list)
    spotify_uri: str = ""
    spotify_id: str = ""

    def key(self) -> str:
        """Normalisoitu tunniste deduplikointia varten."""
        return _normalize(self.artist) + "||" + _normalize(self.title)

    def __str__(self) -> str:
        src = ", ".join(self.sources)
        uri = f" → {self.spotify_uri}" if self.spotify_uri else " (ei Spotifyssa)"
        return f"{self.artist} — {self.title} [{self.score:.1f}p, {src}]{uri}"


# ─── Rakentaja ───────────────────────────────────────────────────────────────

class PlaylistBuilder:
    """
    Kokoaa soittolistan useista lähteistä pisteytysjärjestelmällä.
    """

    def __init__(self) -> None:
        self._pool: dict[str, Candidate] = {}  # key → Candidate
        self.session: dict = {
            "started_at": datetime.now().isoformat(),
            "sources": [],
            "ranked": [],
            "resolved": [],
            "unresolved": [],
            "playlist": None,
        }

    # ─── Lisäys ──────────────────────────────────────────────────────────────

    def add(
        self,
        tracks: list,
        source: str,
        weight: float = 1.0,
    ) -> None:
        """
        Lisää kappaleita pooliin lähteestä.

        tracks: lista diceistä joissa vähintään "artist" ja "title",
                tai objekteja joilla .artist ja .title -attribuutit,
                tai (artist, title) -tupleja.
        source: lähteen nimi lokia varten ("lastfm", "charts", "areena" jne.)
        weight: kerroin — tärkeämmät lähteet saavat suuremman kertoimen
        """
        n = len(tracks)
        if n == 0:
            return

        added = 0
        for i, t in enumerate(tracks):
            artist, title = _extract(t)
            if not artist or not title:
                continue

            # Pistemäärä: ensimmäinen kappale saa weight, viimeinen weight/n
            points = weight * (1.0 - i / n) + weight / n

            key = _normalize(artist) + "||" + _normalize(title)
            if key in self._pool:
                c = self._pool[key]
                c.score += points
                if source not in c.sources:
                    c.sources.append(source)
            else:
                self._pool[key] = Candidate(
                    artist=artist,
                    title=title,
                    score=points,
                    sources=[source],
                )
            added += 1

        self.session["sources"].append({
            "source": source,
            "weight": weight,
            "tracks_in": n,
            "tracks_added": added,
        })

    def add_one(
        self,
        artist: str,
        title: str,
        source: str,
        score: float = 1.0,
    ) -> None:
        """Lisää yksittäinen kappale suoraan pisteellä."""
        key = _normalize(artist) + "||" + _normalize(title)
        if key in self._pool:
            c = self._pool[key]
            c.score += score
            if source not in c.sources:
                c.sources.append(source)
        else:
            self._pool[key] = Candidate(
                artist=artist,
                title=title,
                score=score,
                sources=[source],
            )

    # ─── Pisteytetty lista ───────────────────────────────────────────────────

    def rank(self, limit: int = 50) -> list[Candidate]:
        """
        Palauttaa kandidaatit pisteytysjärjestyksessä.
        Useammasta lähteestä löytyvät kappaleet nousevat automaattisesti.
        """
        ranked = sorted(self._pool.values(), key=lambda c: -c.score)[:limit]
        self.session["ranked"] = [
            {
                "artist": c.artist,
                "title": c.title,
                "score": round(c.score, 2),
                "sources": c.sources,
            }
            for c in ranked
        ]
        return ranked

    # ─── Spotify-resoluutio ──────────────────────────────────────────────────

    def resolve(
        self,
        spotify,
        candidates: list[Candidate],
        market: str = "FI",
    ) -> list[str]:
        """
        Hakee Spotify-URI:t kandidaateille.
        Palauttaa listan spotify:track:xxx -URI:ja (vain löytyneet).
        Tallentaa tulokset session-lokiin.
        """
        uris = []
        for c in candidates:
            uri = _search_spotify(spotify, c.artist, c.title, market)
            if uri:
                c.spotify_uri = uri
                c.spotify_id = uri.split(":")[-1]
                uris.append(uri)
                self.session["resolved"].append({
                    "artist": c.artist,
                    "title": c.title,
                    "uri": uri,
                })
            else:
                self.session["unresolved"].append({
                    "artist": c.artist,
                    "title": c.title,
                })

        return uris

    # ─── Soittolistan luonti ─────────────────────────────────────────────────

    def create(
        self,
        spotify,
        name: str,
        uris: list[str],
        description: str = "",
    ) -> str:
        """
        Luo soittolistan Spotifyyn ja palauttaa URL:n.
        """
        playlist = spotify.create_playlist(name, description=description)
        if uris:
            spotify.add_tracks(playlist["id"], uris)

        url = playlist.get("url", "")
        self.session["playlist"] = {
            "id": playlist["id"],
            "name": name,
            "url": url,
            "track_count": len(uris),
        }
        return url

    # ─── Loki ────────────────────────────────────────────────────────────────

    def save_session(self, path: Path | None = None) -> Path:
        """
        Tallentaa session JSON-lokiin logs/sessions/-kansioon.
        Palauttaa tiedostopolun.
        """
        if path is None:
            logs_dir = Path(__file__).parent.parent / "logs" / "sessions"
            logs_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = logs_dir / f"session_{ts}.json"

        self.session["finished_at"] = datetime.now().isoformat()
        path.write_text(json.dumps(self.session, ensure_ascii=False, indent=2))
        return path

    def summary(self) -> str:
        """Lyhyt tekstiyhteenveto sessiosta."""
        n_sources = len(self.session["sources"])
        n_pool = len(self._pool)
        n_resolved = len(self.session["resolved"])
        n_unresolved = len(self.session["unresolved"])
        playlist = self.session.get("playlist")
        lines = [
            f"Lähteitä: {n_sources}",
            f"Kandidaatteja poolissa: {n_pool}",
            f"Spotify-löydöt: {n_resolved} / {n_resolved + n_unresolved}",
        ]
        if playlist:
            lines.append(f"Soittolista: {playlist['name']} ({playlist['track_count']} kpl)")
            lines.append(f"URL: {playlist['url']}")
        return "\n".join(lines)


# ─── Apufunktiot ─────────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    """Normalisoi merkkijono vertailua varten: lowercase, ei erikoismerkkejä."""
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _extract(t) -> tuple[str, str]:
    """Poimii (artist, title) monesta eri formaatista."""
    if isinstance(t, tuple) and len(t) == 2:
        return str(t[0]), str(t[1])
    if isinstance(t, dict):
        artist = t.get("artist") or t.get("artist_name") or ""
        title = t.get("title") or t.get("track_name") or t.get("name") or ""
        return str(artist), str(title)
    # Dataluokka (SimilarTrack, ChartEntry, Track jne.)
    artist = getattr(t, "artist", "") or getattr(t, "artist_name", "") or ""
    title = getattr(t, "title", "") or getattr(t, "track_name", "") or getattr(t, "name", "") or ""
    return str(artist), str(title)


def _search_spotify(spotify, artist: str, title: str, market: str) -> str:
    """
    Hae Spotify-URI kappaleen nimellä + artistilla.
    Palauttaa URI:n tai tyhjän merkkijonon.
    """
    try:
        query = f"{artist} {title}"
        results = spotify.search_tracks(query, limit=3, market=market)
        if not results:
            return ""
        # Valitse paras osuma: tarkista että artisti täsmää
        artist_norm = _normalize(artist)
        for track in results:
            track_artist = _normalize(getattr(track, "artist", "") or "")
            if artist_norm in track_artist or track_artist in artist_norm:
                return track.uri
        # Fallback: ensimmäinen tulos
        return results[0].uri
    except Exception:
        return ""
