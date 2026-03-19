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
  remove_tracks         → poista kappaleet soittolistasta
  reorder_track         → siirrä kappale toiseen kohtaan soittolistalla
  get_playlist          → hae soittolista ID:llä (referenssiksi)
  get_playlist_tracks   → kaikki kappaleet soittolistalta
  user_playlists        → käyttäjän omat soittolistat
  recently_played       → viimeksi kuunnellut (max 50, scope: recently-played)
  top_tracks            → eniten kuunnellut kappaleet (lyhyt/keski/pitkä aikaväli)
  top_artists           → eniten kuunnellut artistit
  current_user          → kirjautuneen käyttäjän tiedot

Auth: OAuth2 Authorization Code -flow, spotipy hoitaa token-cachetuksen.
Scopes: playlist-modify-public, playlist-modify-private, user-read-private,
        user-read-recently-played, user-top-read
"""

import os
import time
from dataclasses import dataclass, field
from typing import Any

import spotipy
from dotenv import load_dotenv
from pathlib import Path
from spotipy.oauth2 import SpotifyOAuth

load_dotenv(Path(__file__).parent.parent / ".env")

SCOPES = " ".join([
    "playlist-modify-public",
    "playlist-modify-private",
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-read-private",
    "user-read-email",
    "user-read-recently-played",
    "user-top-read",
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-library-read",
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
            if "403" in str(e):
                raise PermissionError(
                    f"Spotify endpoint '{endpoint}' on estetty (403) Development mode -applikaatiolta. "
                    "Nämä endpointit vaativat Extended Quota Moden tai ovat poistettu: "
                    "recommendations, related_artists, artist_top_tracks, audio_features."
                ) from e
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

        try:
            raw = self._call(
                "recommendations[REMOVED]", params,
                self._sp.recommendations, **params,
            )
            return [_parse_track(t) for t in raw["tracks"] if t]
        except spotipy.SpotifyException as e:
            if "404" in str(e):
                raise NotImplementedError(
                    "Spotify /recommendations endpoint on poistettu (404). "
                    "Käytä Last.fm similar_tracks tai ListenBrainz suosituksiin."
                ) from e
            raise

    def available_genre_seeds(self) -> list[str]:
        """
        Lista käytettävissä olevista genre-sedeistä recommendations-endpointille.
        HUOM: /recommendations/available-genre-seeds endpoint on poistettu (404).
        Palautetaan tunnettu lista — toimii recommendations-kutsuissa.
        """
        return [
            "acoustic", "afrobeat", "alt-rock", "alternative", "ambient",
            "anime", "black-metal", "bluegrass", "blues", "bossanova",
            "brazil", "breakbeat", "british", "cantopop", "chicago-house",
            "children", "chill", "classical", "club", "comedy",
            "country", "dance", "dancehall", "death-metal", "deep-house",
            "detroit-techno", "disco", "disney", "drum-and-bass", "dub",
            "dubstep", "edm", "electro", "electronic", "emo",
            "folk", "forro", "french", "funk", "garage",
            "german", "gospel", "goth", "grindcore", "groove",
            "grunge", "guitar", "happy", "hard-rock", "hardcore",
            "hardstyle", "heavy-metal", "hip-hop", "holidays", "honky-tonk",
            "house", "idm", "indian", "indie", "indie-pop",
            "industrial", "iranian", "j-dance", "j-idol", "j-pop",
            "j-rock", "jazz", "k-pop", "kids", "latin",
            "latino", "malay", "mandopop", "metal", "metal-misc",
            "metalcore", "minimal-techno", "movies", "mpb", "new-age",
            "new-release", "opera", "pagode", "party", "philippines-opm",
            "piano", "pop", "pop-film", "post-dubstep", "power-pop",
            "progressive-house", "psych-rock", "punk", "punk-rock", "r-n-b",
            "rainy-day", "reggae", "reggaeton", "road-trip", "rock",
            "rock-n-roll", "rockabilly", "romance", "sad", "salsa",
            "samba", "sertanejo", "show-tunes", "singer-songwriter", "ska",
            "sleep", "songwriter", "soul", "soundtracks", "spanish",
            "study", "summer", "swedish", "synth-pop", "tango",
            "techno", "trance", "trip-hop", "turkish", "work-out", "world-music",
        ]

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
        raw = self._call(
            "create_playlist", {"name": name, "public": public},
            self._sp.current_user_playlist_create,
            name=name, public=public, description=description,
        )
        return {
            "id": raw["id"],
            "uri": raw["uri"],
            "url": raw["external_urls"]["spotify"],
            "name": raw["name"],
        }

    def add_tracks(self, playlist_id: str, track_uris: list[str]) -> None:
        """Lisää kappaleet soittolistaan. Max 100 per kutsu — splitataan automaattisesti."""
        for chunk in _chunks(track_uris, 100):
            self._call(
                "add_items_to_playlist", {"playlist_id": playlist_id, "count": len(chunk)},
                self._sp.playlist_add_items, playlist_id, chunk,
            )

    def remove_tracks(self, playlist_id: str, track_uris: list[str]) -> None:
        """Poista kappaleet soittolistasta URI-listan perusteella."""
        for chunk in _chunks(track_uris, 100):
            self._call(
                "remove_playlist_items", {"playlist_id": playlist_id, "count": len(chunk)},
                self._sp.playlist_remove_all_occurrences_of_items, playlist_id, chunk,
            )

    def reorder_track(self, playlist_id: str, from_pos: int, to_pos: int) -> None:
        """Siirrä kappale pozitsiosta from_pos pozistioon to_pos."""
        self._call(
            "reorder_playlist", {"playlist_id": playlist_id, "from": from_pos, "to": to_pos},
            self._sp.playlist_reorder_items, playlist_id, from_pos, to_pos,
        )

    def get_playlist(self, playlist_id: str) -> dict:
        """
        Hae soittolista ID:llä. Käytetään referenssiksi ("tehtiin X soittolista").
        Palauttaa: {id, name, description, owner, track_count, url}
        """
        raw = self._call(
            "get_playlist", {"playlist_id": playlist_id},
            self._sp.playlist, playlist_id,
        )
        return {
            "id": raw["id"],
            "name": raw["name"],
            "description": raw.get("description", ""),
            "owner": raw["owner"]["display_name"],
            "track_count": raw.get("tracks", {}).get("total", 0),
            "url": raw["external_urls"]["spotify"],
            "uri": raw["uri"],
            "public": raw.get("public", False),
        }

    def get_playlist_tracks(self, playlist_id: str, limit: int = 100) -> list[Track]:
        """Hae kaikki kappaleet soittolistalta (hakee kaikki sivut automaattisesti)."""
        tracks = []
        offset = 0
        while True:
            raw = self._call(
                "get_playlist_items",
                {"playlist_id": playlist_id, "offset": offset, "limit": limit},
                self._sp.playlist_items, playlist_id, limit=limit, offset=offset,
            )
            items = raw.get("items", [])
            for item in items:
                # Spotify palauttaa joko "track" tai "item" avaimella versiosta riippuen
                t = item.get("track") or item.get("item")
                if t and isinstance(t, dict) and t.get("id"):
                    tracks.append(_parse_track(t))
            if raw.get("next") is None:
                break
            offset += limit
        return tracks

    def user_playlists(self, limit: int = 50) -> list[dict]:
        """
        Käyttäjän omat soittolistat. Käytetään referenssiksi —
        "tehtiin X soittolista" → haetaan ID nimellä.
        """
        raw = self._call(
            "user_playlists", {"limit": limit},
            self._sp.current_user_playlists, limit=limit,
        )
        return [
            {
                "id": p["id"],
                "name": p["name"],
                "description": p.get("description", ""),
                "url": p.get("external_urls", {}).get("spotify", ""),
                "public": p.get("public", False),
            }
            for p in raw["items"] if p
        ]

    def find_playlist_by_name(self, name: str) -> dict | None:
        """Etsi soittolista nimellä käyttäjän listoista. Palauttaa ensimmäisen osuman tai None."""
        playlists = self.user_playlists(limit=50)
        name_lower = name.lower()
        for p in playlists:
            if name_lower in p["name"].lower():
                return p
        return None

    # ─── Kuunteluhistoria ─────────────────────────────────────────────────────

    def recently_played(self, limit: int = 50) -> list[dict]:
        """
        Viimeksi kuunnellut kappaleet (max 50).
        Scope: user-read-recently-played
        Palauttaa: [{track, played_at}]
        """
        raw = self._call(
            "recently_played", {"limit": limit},
            self._sp.current_user_recently_played, limit=limit,
        )
        return [
            {
                "track": _parse_track(item["track"]),
                "played_at": item["played_at"],
            }
            for item in raw.get("items", []) if item.get("track")
        ]

    def top_tracks(self, time_range: str = "medium_term", limit: int = 50) -> list[Track]:
        """
        Eniten kuunnellut kappaleet.
        time_range: "short_term" (4vk) | "medium_term" (6kk) | "long_term" (vuosia)
        Scope: user-top-read
        """
        raw = self._call(
            "top_tracks", {"time_range": time_range, "limit": limit},
            self._sp.current_user_top_tracks, time_range=time_range, limit=limit,
        )
        return [_parse_track(t) for t in raw.get("items", []) if t]

    def top_artists(self, time_range: str = "medium_term", limit: int = 20) -> list[dict]:
        """
        Eniten kuunnellut artistit.
        time_range: "short_term" (4vk) | "medium_term" (6kk) | "long_term" (vuosia)
        Scope: user-top-read
        """
        raw = self._call(
            "top_artists", {"time_range": time_range, "limit": limit},
            self._sp.current_user_top_artists, time_range=time_range, limit=limit,
        )
        return [_parse_artist(a) for a in raw.get("items", []) if a]

    # ─── Toistohallinta ───────────────────────────────────────────────────────

    def currently_playing(self) -> dict | None:
        """
        Mitä soi juuri nyt.
        Palauttaa: {track, is_playing, progress_ms, device} tai None jos ei soi.
        Scope: user-read-playback-state
        """
        raw = self._call("currently_playing", {}, self._sp.currently_playing)
        if not raw or not raw.get("item"):
            return None
        return {
            "track": _parse_track(raw["item"]),
            "is_playing": raw.get("is_playing", False),
            "progress_ms": raw.get("progress_ms", 0),
            "device": raw.get("device", {}).get("name", "?"),
        }

    def queue_track(self, uri: str) -> None:
        """
        Lisää kappale Spotifyn jonoon (soi nykyisen jälkeen).
        uri: Spotify track URI, esim. "spotify:track:4iV5W9uYEdYUVa79Axb7Rh"
        Scope: user-modify-playback-state
        Vaatii aktiivisen laitteen (Spotify auki).
        """
        self._call("add_to_queue", {"uri": uri}, self._sp.add_to_queue, uri)

    def play_now(self, uris: list[str]) -> None:
        """
        Aloita toisto välittömästi annetuilla kappaleilla.
        uris: lista Spotify track URI:eja — toistetaan järjestyksessä.
        Scope: user-modify-playback-state
        Vaatii aktiivisen laitteen.
        """
        self._call(
            "start_playback", {"uris": uris},
            self._sp.start_playback, uris=uris,
        )

    def active_devices(self) -> list[dict]:
        """
        Lista aktiivisista Spotify-laitteista.
        Palauttaa: [{id, name, type, is_active, volume_percent}]
        Scope: user-read-playback-state
        """
        raw = self._call("devices", {}, self._sp.devices)
        return [
            {
                "id": d["id"],
                "name": d["name"],
                "type": d["type"],
                "is_active": d["is_active"],
                "volume_percent": d.get("volume_percent", 0),
            }
            for d in (raw or {}).get("devices", [])
        ]

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
