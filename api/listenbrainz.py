"""
ListenBrainz API wrapper.

Mitä ListenBrainzista saadaan:
  similar_users            → samankaltaiset kuuntelijat → heidän suosikkinsa
  user_listens             → käyttäjän kuunteluhistoria (viimeisimmät)
  user_top_artists         → käyttäjän kuunnelluimmat artistit
  user_top_recordings      → käyttäjän kuunnelluimmat kappaleet
  recommendation_recordings → henkilökohtaiset kappaleehdotukset (MBID-pohjainen)

Arvokkain data:
  - recommendation_recordings: suoraan soittolista-ehdotukset käyttäjälle
  - user_top_artists / user_top_recordings: mitä käyttäjä oikeasti kuuntelee
  - Kaikki data on MBID-pohjaista → yhdistettävissä MusicBrainziin

Autentikaatio: LB_TOKEN ympäristömuuttujassa (tarvitaan recommendation_recordingsiin)
Muihin hakuihin token ei tarvita.
"""

import os
import time
from dataclasses import dataclass

import httpx
import liblistenbrainz
from dotenv import load_dotenv
from pathlib import Path

LB_API_BASE = "https://api.listenbrainz.org"

load_dotenv(Path(__file__).parent.parent / ".env")

LB_USERNAME = "mokkatrukki"   # oletuslukija jos ei anneta


# ─── Dataluokat ──────────────────────────────────────────────────────────────

@dataclass
class ApiCall:
    endpoint: str
    params: dict
    result_count: int
    latency_ms: float
    error: str | None = None


# ─── Asiakas ─────────────────────────────────────────────────────────────────

class ListenBrainzClient:
    """
    ListenBrainz-wrapper liblistenbrainz:n päälle.
    """

    def __init__(self) -> None:
        self._lb = liblistenbrainz.ListenBrainz()
        token = os.getenv("LB_TOKEN")
        if token:
            self._lb.set_auth_token(token)
        self.call_log: list[ApiCall] = []

    def _call(self, endpoint: str, params: dict, fn, *args, **kwargs):
        t0 = time.monotonic()
        error = None
        result = None
        try:
            result = fn(*args, **kwargs)
        except liblistenbrainz.errors.ListenBrainzAPIException as e:
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

    # ─── Suositukset ─────────────────────────────────────────────────────────

    def recommendation_recordings(
        self,
        username: str = LB_USERNAME,
        artist_type: str = "top",   # "top" | "similar"
        count: int = 25,
    ) -> list[dict]:
        """
        Henkilökohtaiset kappaleehdotukset ListenBrainzin ML-mallilta.
        artist_type="top"     → suositeltu käyttäjän top-artistien pohjalta
        artist_type="similar" → suositeltu samankaltaisten kuuntelijoiden pohjalta
        Palauttaa: [{mbid, recording_mbid, artist, title, score}]
        Vaatii LB_TOKEN:n.
        """
        raw = self._call(
            "recommendations.cf.recording.get_user_recommendations",
            {"username": username, "artist_type": artist_type, "count": count},
            self._lb.get_user_recommendation_recordings,
            username,
            artist_type=artist_type,
            count=count,
        )
        if not raw:
            return []
        out = []
        for item in (raw or []):
            mbid = ""
            recording_mbid = ""
            artist = ""
            title = ""
            score = 0.0

            if hasattr(item, "track_metadata"):
                meta = item.track_metadata
                artist = getattr(meta, "artist_name", "")
                title = getattr(meta, "track_name", "")
                info = getattr(meta, "additional_info", None)
                if info:
                    recording_mbid = getattr(info, "recording_mbid", "") or ""
            if hasattr(item, "score"):
                score = float(item.score or 0)

            out.append({
                "recording_mbid": recording_mbid,
                "artist": artist,
                "title": title,
                "score": score,
            })
        return out

    # ─── Uudet julkaisut ─────────────────────────────────────────────────────

    def fresh_releases(
        self,
        days: int = 30,
        sort: str = "listen_count",  # "listen_count" | "release_date"
        limit: int = 100,
    ) -> list[dict]:
        """
        Tuoreet julkaisut ListenBrainzin Fresh Releases -feedistä.
        sort="listen_count" → nousevat (eniten kuunneltuja uusista julkaisuista)
        sort="release_date" → uusimmat ensin (enemmän harvinaisia)

        Palauttaa: [{
            artist: str,
            album: str,
            release_date: str,  # "2026-03-15"
            release_mbid: str,
            release_type: str,  # "Album" | "Single" | "EP" | ...
            tags: list[str],
            listen_count: int,
        }]
        """
        t0 = time.monotonic()
        error = None
        releases = []
        try:
            # API tukee vain sort=release_date — listen_count-sorttaus tehdään client-side
            api_sort = "release_date" if sort == "listen_count" else sort
            r = httpx.get(
                f"{LB_API_BASE}/1/explore/fresh-releases/",
                params={"days": days, "sort": api_sort},
                timeout=30,
            )
            r.raise_for_status()
            raw = r.json().get("payload", {}).get("releases", [])
            for item in raw:
                releases.append({
                    "artist": item.get("artist_credit_name", ""),
                    "album": item.get("release_name", ""),
                    "release_date": item.get("release_date", ""),
                    "release_mbid": item.get("release_mbid", ""),
                    "release_type": item.get("release_group_primary_type", ""),
                    "tags": item.get("release_tags", []),
                    "listen_count": item.get("listen_count", 0) or 0,
                })
            if sort == "listen_count":
                releases.sort(key=lambda x: x["listen_count"], reverse=True)
        except Exception as e:
            error = str(e)
            raise
        finally:
            latency = (time.monotonic() - t0) * 1000
            self.call_log.append(ApiCall(
                endpoint="explore.fresh-releases",
                params={"days": days, "sort": sort},
                result_count=len(releases),
                latency_ms=round(latency, 1),
                error=error,
            ))
        return releases[:limit]

    # ─── Käyttäjädata ────────────────────────────────────────────────────────

    def user_listens(
        self,
        username: str = LB_USERNAME,
        count: int = 25,
    ) -> list[dict]:
        """
        Käyttäjän viimeisimmät kuuntelut.
        Palauttaa: [{artist, title, recording_mbid, listened_at}]
        """
        raw = self._call(
            "user.getListens",
            {"username": username, "count": count},
            self._lb.get_listens,
            username,
            count=count,
        )
        out = []
        for listen in (raw or []):
            meta = getattr(listen, "track_metadata", None)
            if not meta:
                continue
            info = getattr(meta, "additional_info", None)
            out.append({
                "artist": getattr(meta, "artist_name", ""),
                "title": getattr(meta, "track_name", ""),
                "recording_mbid": getattr(info, "recording_mbid", "") if info else "",
                "listened_at": getattr(listen, "listened_at", None),
            })
        return out

    def user_top_artists(
        self,
        username: str = LB_USERNAME,
        count: int = 25,
        time_range: str = "all_time",   # "all_time" | "month" | "week" | "year"
    ) -> list[dict]:
        """
        Käyttäjän kuunnelluimmat artistit.
        Palauttaa: [{artist, artist_mbid, listen_count}]
        """
        raw = self._call(
            "stats.user.artists",
            {"username": username, "count": count, "time_range": time_range},
            self._lb.get_user_artists,
            username,
            count=count,
            time_range=time_range,
        )
        out = []
        for item in (raw or []):
            out.append({
                "artist": getattr(item, "artist_name", ""),
                "artist_mbid": (getattr(item, "artist_mbids", None) or [""])[0],
                "listen_count": getattr(item, "listen_count", 0),
            })
        return out

    def user_top_recordings(
        self,
        username: str = LB_USERNAME,
        count: int = 25,
        time_range: str = "all_time",
    ) -> list[dict]:
        """
        Käyttäjän kuunnelluimmat kappaleet.
        Palauttaa: [{artist, title, recording_mbid, listen_count}]
        """
        raw = self._call(
            "stats.user.recordings",
            {"username": username, "count": count, "time_range": time_range},
            self._lb.get_user_recordings,
            username,
            count=count,
            time_range=time_range,
        )
        out = []
        for item in (raw or []):
            out.append({
                "artist": getattr(item, "artist_name", ""),
                "title": getattr(item, "track_name", ""),
                "recording_mbid": getattr(item, "recording_mbid", "") or "",
                "listen_count": getattr(item, "listen_count", 0),
            })
        return out

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
                    **({("error"): c.error} if c.error else {}),
                }
                for c in self.call_log
            ],
        }
