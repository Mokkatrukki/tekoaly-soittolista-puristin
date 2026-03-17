"""
Spotify API wrapper.

Endpointit joita käytetään:
  search                → hae kappaleita/artisteja nimellä
  artist_top_tracks     → artistin suosituimmat kappaleet
  related_artists       → samankaltaiset artistit
  audio_features        → kappaleen audio-ominaisuudet (tempo, energy, valence...)
  recommendations       → DEPRECATED mutta toimii — seed-pohjainen suosittelu
  create_playlist       → luo uusi soittolista käyttäjälle
  add_tracks            → lisää kappaleet soittolistaan
  current_user          → kirjautuneen käyttäjän tiedot

Auth: OAuth2 Authorization Code -flow, spotipy hoitaa token-cachetuksen.
Scopes: playlist-modify-public, playlist-modify-private, user-read-private
"""

import os
import time
from dataclasses import dataclass, field
from typing import Any

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

SCOPES = " ".join([
    "playlist-modify-public",
    "playlist-modify-private",
    "user-read-private",
    "user-read-email",
])


# ─── Dataluokat ──────────────────────────────────────────────────────────────

@dataclass
class Track:
    id: str
    uri: str
    name: str
    artist: str
    artist_id: str
    album: str
    duration_ms: int
    score: float = 0.0          # pisteytysjärjestelmä: useampi lähde = korkeampi
    sources: list[str] = field(default_factory=list)  # mistä lähteistä löytyi

    def __str__(self) -> str:
        return f"{self.artist} — {self.name}"


@dataclass
class AudioFeatures:
    track_id: str
    danceability: float     # 0.0–1.0
    energy: float           # 0.0–1.0
    valence: float          # 0.0–1.0 (positiivisuus/iloisuus)
    tempo: float            # BPM
    acousticness: float     # 0.0–1.0
    instrumentalness: float # 0.0–1.0
    speechiness: float      # 0.0–1.0
    loudness: float         # dB, tyypillisesti -60–0
    key: int                # 0=C, 1=C#/Db, ... 11=B
    mode: int               # 0=minor, 1=major
    time_signature: int     # 3, 4, 5, 6, 7


# ─── Logiapuri ───────────────────────────────────────────────────────────────

@dataclass
class ApiCall:
    endpoint: str
    params: dict
    result_count: int
    latency_ms: float
    error: str | None = None


class SpotifyClient:
    """
    Spotify-wrapper sessioita varten.
    Lokkaa kaikki API-kutsut myöhempää optimointia varten.
    """

    def __init__(self) -> None:
        self._sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=os.getenv("SPOTIFY_CLIENT_ID"),
            client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
            redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8000/auth/callback"),
            scope=SCOPES,
            cache_path=".spotify_token_cache",
            open_browser=True,
        ))
        self.call_log: list[ApiCall] = []

    def _call(self, endpoint: str, params: dict, fn, *args, **kwargs) -> Any:
        """Ajaa API-kutsun ja lokkaa sen."""
        t0 = time.monotonic()
        error = None
        result = None
        try:
            result = fn(*args, **kwargs)
        except spotipy.SpotifyException as e:
            error = str(e)
            raise
        finally:
            latency = (time.monotonic() - t0) * 1000
            count = 0
            if result:
                if isinstance(result, list):
                    count = len(result)
                elif isinstance(result, dict):
                    # Yritä löytää items-lista
                    for key in ("tracks", "artists", "items"):
                        if key in result:
                            inner = result[key]
                            count = len(inner.get("items", inner) if isinstance(inner, dict) else inner)
                            break
            self.call_log.append(ApiCall(
                endpoint=endpoint,
                params=params,
                result_count=count,
                latency_ms=round(latency, 1),
                error=error,
            ))
        return result

    # ─── Haku ────────────────────────────────────────────────────────────────

    def search_tracks(self, query: str, limit: int = 10, market: str = "FI") -> list[Track]:
        """Hae kappaleita hakusanalla. Palauttaa Track-listan."""
        raw = self._call(
            "search:tracks", {"q": query, "limit": limit},
            self._sp.search, q=query, type="track", limit=limit, market=market,
        )
        return [_parse_track(t) for t in raw["tracks"]["items"] if t]

    def search_artists(self, query: str, limit: int = 5) -> list[dict]:
        """Hae artisteja. Palauttaa [{id, name, genres, popularity}]."""
        raw = self._call(
            "search:artists", {"q": query, "limit": limit},
            self._sp.search, q=query, type="artist", limit=limit,
        )
        return [_parse_artist(a) for a in raw["artists"]["items"] if a]

    # ─── Artisti ─────────────────────────────────────────────────────────────

    def artist_top_tracks(self, artist_id: str, market: str = "FI") -> list[Track]:
        """Artistin top-10 kappaletta annetulla markkina-alueella."""
        raw = self._call(
            "artist_top_tracks", {"id": artist_id, "market": market},
            self._sp.artist_top_tracks, artist_id, country=market,
        )
        return [_parse_track(t) for t in raw["tracks"] if t]

    def related_artists(self, artist_id: str) -> list[dict]:
        """Spotifyn samankaltaiset artistit (max 20)."""
        raw = self._call(
            "related_artists", {"id": artist_id},
            self._sp.artist_related_artists, artist_id,
        )
        return [_parse_artist(a) for a in raw["artists"] if a]

    def artist_info(self, artist_id: str) -> dict:
        """Artistin perustiedot: nimi, genret, followers."""
        raw = self._call(
            "artist_info", {"id": artist_id},
            self._sp.artist, artist_id,
        )
        return _parse_artist(raw)

    # ─── Audio features ──────────────────────────────────────────────────────

    def audio_features(self, track_ids: list[str]) -> list[AudioFeatures]:
        """
        Hakee audio features usealle kappaleelle kerralla (max 100).
        Käyttö: energiataso, tempo, tunnelma (valence) jne.
        """
        results = []
        for chunk in _chunks(track_ids, 100):
            raw = self._call(
                "audio_features", {"ids": chunk},
                self._sp.audio_features, chunk,
            )
            for af in (raw or []):
                if af:
                    results.append(_parse_audio_features(af))
        return results

    # ─── Suositukset (DEPRECATED mutta toimii) ───────────────────────────────

    def recommendations(
        self,
        seed_artists: list[str] | None = None,
        seed_tracks: list[str] | None = None,
        seed_genres: list[str] | None = None,
        limit: int = 20,
        **audio_filters,  # target_energy=0.8, min_valence=0.5 jne.
    ) -> list[Track]:
        """
        Spotify-suositukset seed-pohjaisten parametrien avulla.

        HUOM: Endpoint on DEPRECATED — Spotify saattaa poistaa sen.
        Yhteensä max 5 seediä (artists + tracks + genres).

        audio_filters esimerkit:
            target_energy=0.7
            target_valence=0.6
            min_tempo=120, max_tempo=140
            target_danceability=0.8
        """
        seeds_total = len(seed_artists or []) + len(seed_tracks or []) + len(seed_genres or [])
        if seeds_total == 0:
            raise ValueError("Vähintään yksi seed vaaditaan (artists, tracks tai genres)")
        if seeds_total > 5:
            raise ValueError(f"Max 5 seediä yhteensä, annettiin {seeds_total}")

        params: dict[str, Any] = {"limit": limit}
        if seed_artists:
            params["seed_artists"] = seed_artists
        if seed_tracks:
            params["seed_tracks"] = seed_tracks
        if seed_genres:
            params["seed_genres"] = seed_genres
        params.update(audio_filters)

        raw = self._call(
            "recommendations[DEPRECATED]", params,
            self._sp.recommendations, **params,
        )
        return [_parse_track(t) for t in raw["tracks"] if t]

    def available_genre_seeds(self) -> list[str]:
        """Lista käytettävissä olevista genre-sedeistä recommendations-endpointille."""
        raw = self._call(
            "genre_seeds", {},
            self._sp.recommendation_genre_seeds,
        )
        return raw["genres"]

    # ─── Soittolista ─────────────────────────────────────────────────────────

    def current_user_id(self) -> str:
        """Kirjautuneen käyttäjän Spotify-ID."""
        raw = self._call("current_user", {}, self._sp.current_user)
        return raw["id"]

    def create_playlist(
        self,
        name: str,
        description: str = "",
        public: bool = False,
    ) -> dict:
        """
        Luo uusi soittolista kirjautuneelle käyttäjälle.
        Palauttaa: {id, uri, url}
        """
        user_id = self.current_user_id()
        raw = self._call(
            "create_playlist", {"name": name, "public": public},
            self._sp.user_playlist_create,
            user=user_id, name=name, public=public, description=description,
        )
        return {
            "id": raw["id"],
            "uri": raw["uri"],
            "url": raw["external_urls"]["spotify"],
            "name": raw["name"],
        }

    def add_tracks(self, playlist_id: str, track_uris: list[str]) -> None:
        """
        Lisää kappaleet soittolistaan. Max 100 per kutsu — splitataan automaattisesti.
        """
        for chunk in _chunks(track_uris, 100):
            self._call(
                "add_items_to_playlist", {"playlist_id": playlist_id, "count": len(chunk)},
                self._sp.playlist_add_items, playlist_id, chunk,
            )

    # ─── Loki ────────────────────────────────────────────────────────────────

    def log_summary(self) -> dict:
        """Palauttaa yhteenvedon kaikista session API-kutsuista lokitusta varten."""
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


# ─── Parserit ────────────────────────────────────────────────────────────────

def _parse_track(raw: dict) -> Track:
    artists = raw.get("artists", [])
    return Track(
        id=raw["id"],
        uri=raw["uri"],
        name=raw["name"],
        artist=artists[0]["name"] if artists else "?",
        artist_id=artists[0]["id"] if artists else "",
        album=raw.get("album", {}).get("name", ""),
        duration_ms=raw.get("duration_ms", 0),
    )


def _parse_artist(raw: dict) -> dict:
    return {
        "id": raw["id"],
        "name": raw["name"],
        "genres": raw.get("genres", []),
        "followers": raw.get("followers", {}).get("total", 0),
        "uri": raw.get("uri", ""),
    }


def _parse_audio_features(raw: dict) -> AudioFeatures:
    return AudioFeatures(
        track_id=raw["id"],
        danceability=raw["danceability"],
        energy=raw["energy"],
        valence=raw["valence"],
        tempo=raw["tempo"],
        acousticness=raw["acousticness"],
        instrumentalness=raw["instrumentalness"],
        speechiness=raw["speechiness"],
        loudness=raw["loudness"],
        key=raw["key"],
        mode=raw["mode"],
        time_signature=raw["time_signature"],
    )


def _chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]
