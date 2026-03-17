"""
Last.fm API wrapper.

Endpointit:
  similar_tracks    → samankaltaiset kappaleet (tärkein discovery-työkalu)
  similar_artists   → samankaltaiset artistit + match-arvo (0–1)
  artist_top_tracks → artistin kuunnelluimmat kappaleet
  track_info        → kappaleen metatiedot + kuuntelijamäärä
  artist_tags       → artistin top-tagit (genre-signaali)
  tag_top_tracks    → tietyllä tagilla merkityt suosituimmat kappaleet
  tag_top_artists   → tietyllä tagilla merkityt suosituimmat artistit

Ei vaadi autentikaatiota — pelkkä API-avain riittää.
Dokumentaatio: https://www.last.fm/api (käytä fetch_doc("lastfm.*"))
"""

import os
import time
from dataclasses import dataclass, field

import pylast
from dotenv import load_dotenv

load_dotenv()


# ─── Dataluokat ──────────────────────────────────────────────────────────────

@dataclass
class SimilarTrack:
    artist: str
    title: str
    match: float        # 0.0–1.0 samankaltaisuus
    mbid: str = ""      # MusicBrainz ID jos saatavilla

    def __str__(self) -> str:
        return f"{self.artist} — {self.title} (match: {self.match:.2f})"


@dataclass
class SimilarArtist:
    name: str
    match: float        # 0.0–1.0
    mbid: str = ""

    def __str__(self) -> str:
        return f"{self.name} (match: {self.match:.2f})"


@dataclass
class ApiCall:
    endpoint: str
    params: dict
    result_count: int
    latency_ms: float
    error: str | None = None


# ─── Asiakas ─────────────────────────────────────────────────────────────────

class LastFmClient:
    """
    Last.fm-wrapper pylast:n päälle.
    Lokkaa kaikki kutsut samaan tapaan kuin SpotifyClient.
    """

    def __init__(self) -> None:
        self._network = pylast.LastFMNetwork(
            api_key=os.getenv("LASTFM_API_KEY"),
        )
        self.call_log: list[ApiCall] = []

    def _call(self, endpoint: str, params: dict, fn, *args, **kwargs):
        t0 = time.monotonic()
        error = None
        result = None
        try:
            result = fn(*args, **kwargs)
        except pylast.WSError as e:
            error = str(e)
            raise
        finally:
            latency = (time.monotonic() - t0) * 1000
            count = len(result) if isinstance(result, list) else (1 if result else 0)
            self.call_log.append(ApiCall(
                endpoint=endpoint,
                params=params,
                result_count=count,
                latency_ms=round(latency, 1),
                error=error,
            ))
        return result

    # ─── Samankaltaisuus ─────────────────────────────────────────────────────

    def similar_tracks(
        self,
        artist: str,
        title: str,
        limit: int = 30,
    ) -> list[SimilarTrack]:
        """
        Samankaltaiset kappaleet kuunteludatan perusteella.
        Tärkein Last.fm discovery-työkalu.
        Palauttaa listan match-arvolla 0–1 järjestettynä.
        """
        track = self._network.get_track(artist, title)
        raw = self._call(
            "track.getSimilar",
            {"artist": artist, "title": title, "limit": limit},
            track.get_similar,
            limit=limit,
        )
        return [
            SimilarTrack(
                artist=str(item.item.artist),
                title=str(item.item.title),
                match=float(item.match),
                mbid=item.item.get_mbid() or "",
            )
            for item in (raw or [])
        ]

    def similar_artists(
        self,
        artist: str,
        limit: int = 20,
    ) -> list[SimilarArtist]:
        """
        Samankaltaiset artistit.
        match-arvo 0–1: 1 = hyvin samankaltainen.
        """
        a = self._network.get_artist(artist)
        raw = self._call(
            "artist.getSimilar",
            {"artist": artist, "limit": limit},
            a.get_similar,
            limit=limit,
        )
        return [
            SimilarArtist(
                name=str(item.item.name),
                match=float(item.match),
                mbid=item.item.get_mbid() or "",
            )
            for item in (raw or [])
        ]

    # ─── Artisti ─────────────────────────────────────────────────────────────

    def artist_top_tracks(self, artist: str, limit: int = 20) -> list[dict]:
        """
        Artistin kuunnelluimmat kappaleet Last.fm-datan perusteella.
        Palauttaa: [{title, playcount, listeners}]
        """
        a = self._network.get_artist(artist)
        raw = self._call(
            "artist.getTopTracks",
            {"artist": artist, "limit": limit},
            a.get_top_tracks,
            limit=limit,
        )
        result = []
        for item in (raw or []):
            t = item.item
            result.append({
                "title": str(t.title),
                "artist": str(t.artist),
                "playcount": int(item.weight),
            })
        return result

    def artist_tags(self, artist: str, limit: int = 10) -> list[str]:
        """
        Artistin top-tagit — genresignaali.
        Esim: ["jazz", "hip-hop", "instrumental", "japanese"]
        """
        a = self._network.get_artist(artist)
        raw = self._call(
            "artist.getTopTags",
            {"artist": artist},
            a.get_top_tags,
            limit=limit,
        )
        return [str(item.item.name).lower() for item in (raw or [])][:limit]

    # ─── Track info ──────────────────────────────────────────────────────────

    def track_info(self, artist: str, title: str) -> dict:
        """
        Kappaleen metatiedot: kuuntelijat, soittokerrat, tagit.
        Palauttaa: {artist, title, listeners, playcount, tags, url}
        """
        t = self._network.get_track(artist, title)
        raw = self._call(
            "track.getInfo",
            {"artist": artist, "title": title},
            t.get_wiki_summary,  # triggeröi API-kutsu
        )
        listeners = 0
        playcount = 0
        try:
            listeners = t.get_listener_count()
            playcount = t.get_playcount()
        except Exception:
            pass

        tags = []
        try:
            top_tags = t.get_top_tags(limit=5)
            tags = [str(tag.item.name).lower() for tag in top_tags]
        except Exception:
            pass

        return {
            "artist": artist,
            "title": title,
            "listeners": listeners,
            "playcount": playcount,
            "tags": tags,
            "summary": raw or "",
        }

    # ─── Tagit ───────────────────────────────────────────────────────────────

    def tag_top_tracks(self, tag: str, limit: int = 50) -> list[dict]:
        """
        Tietyllä tagilla merkityt suosituimmat kappaleet.
        Hyödyllinen kun käyttäjä mainitsee genren nimeltä.
        Palauttaa: [{artist, title, rank}]
        """
        t = self._network.get_tag(tag)
        raw = self._call(
            "tag.getTopTracks",
            {"tag": tag, "limit": limit},
            t.get_top_tracks,
            limit=limit,
        )
        return [
            {
                "artist": str(item.item.artist),
                "title": str(item.item.title),
                "rank": int(item.weight),
            }
            for item in (raw or [])
        ]

    def tag_top_artists(self, tag: str, limit: int = 30) -> list[dict]:
        """
        Tietyllä tagilla merkityt suosituimmat artistit.
        Palauttaa: [{name, rank}]
        """
        t = self._network.get_tag(tag)
        raw = self._call(
            "tag.getTopArtists",
            {"tag": tag, "limit": limit},
            t.get_top_artists,
            limit=limit,
        )
        return [
            {
                "name": str(item.item.name),
                "rank": int(item.weight),
            }
            for item in (raw or [])
        ]

    # ─── Loki ────────────────────────────────────────────────────────────────

    def log_summary(self) -> dict:
        return {
            "total_calls": len(self.call_log),
            "total_latency_ms": round(sum(c.latency_ms for c in self.call_log), 1),
            "calls": [
                {
                    "endpoint": c.endpoint,
                    "params": c.params,
                    "results": c.result_count,
                    "latency_ms": c.latency_ms,
                    **({"error": c.error} if c.error else {}),
                }
                for c in self.call_log
            ],
        }
