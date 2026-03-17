"""
Discogs API wrapper.

Mitä Discogsista saadaan soittolistan rakentamiseen:
  search          → hae artisteja/releaseja nimellä → saa Discogs-ID:n
  release         → genres, styles, year, country, tracklist, yhteisöarvosana
  master          → master-release: kaikki painokset koottuna, genres, styles
  artist          → artistin profiili, aliakset
  artist_releases → artistin kaikki julkaisut (filtteröi tyypeittäin)

Arvokkain data:
  - styles (tarkka genre, esim. "Acid House", "Cosmic Disco", "Dungeon Synth")
  - community.rating.average — laatu-indikaattori
  - community.have / community.want — suosio/keräilyarvo
  - year — aikakausi
  - country — alkuperämaa

Autentikaatio: token (DISCOGS_TOKEN ympäristömuuttujassa)
User-Agent vaaditaan: asetetaan automaattisesti
"""

import os
import time
from dataclasses import dataclass

import discogs_client
from dotenv import load_dotenv

load_dotenv()

USER_AGENT = "SoittolistaPuristin/0.1"


# ─── Dataluokat ──────────────────────────────────────────────────────────────

@dataclass
class ReleaseInfo:
    id: int
    title: str
    artist: str
    year: int | None
    country: str
    genres: list[str]
    styles: list[str]          # tarkempi kuin genres
    rating: float              # 0–5 yhteisöarvosana
    have: int                  # kuinka monella on
    want: int                  # kuinka moni haluaa
    tracklist: list[str]       # kappaleiden nimet

    def style_tags(self) -> list[str]:
        """Kaikki genre+style -tagit yhtenä listana, lowercase."""
        return [t.lower() for t in self.genres + self.styles]


@dataclass
class ApiCall:
    endpoint: str
    params: dict
    result_count: int
    latency_ms: float
    error: str | None = None


# ─── Asiakas ─────────────────────────────────────────────────────────────────

class DiscogsClient:
    """
    Discogs-wrapper discogs_client:n päälle.
    """

    def __init__(self) -> None:
        self._d = discogs_client.Client(
            USER_AGENT,
            user_token=os.getenv("DISCOGS_TOKEN"),
        )
        self.call_log: list[ApiCall] = []

    def _time(self, endpoint: str, params: dict, fn, *args, **kwargs):
        t0 = time.monotonic()
        error = None
        result = None
        try:
            result = fn(*args, **kwargs)
        except Exception as e:
            error = str(e)
            raise
        finally:
            latency = (time.monotonic() - t0) * 1000
            count = len(result) if hasattr(result, "__len__") else 1
            self.call_log.append(ApiCall(
                endpoint=endpoint,
                params=params,
                result_count=count,
                latency_ms=round(latency, 1),
                error=error,
            ))
        return result

    # ─── Haku ────────────────────────────────────────────────────────────────

    def search_release(self, query: str, limit: int = 5) -> list[dict]:
        """
        Hae releaseja hakusanalla.
        Palauttaa: [{id, title, artist, year, genres, styles, country}]
        Käytetään ensin Discogs-ID:n löytämiseen, sitten haetaan tarkemmat tiedot.
        """
        results = self._time(
            "database.search[release]", {"q": query, "type": "release", "limit": limit},
            self._d.search, query, type="release",
        )
        out = []
        for r in list(results)[:limit]:
            try:
                out.append({
                    "id": r.id,
                    "title": r.title,
                    "year": getattr(r, "year", None),
                    "genres": list(getattr(r, "genres", []) or []),
                    "styles": list(getattr(r, "styles", []) or []),
                    "country": getattr(r, "country", ""),
                })
            except Exception:
                continue
        return out

    def search_artist(self, query: str, limit: int = 5) -> list[dict]:
        """
        Hae artisteja nimellä.
        Palauttaa: [{id, name}]
        """
        results = self._time(
            "database.search[artist]", {"q": query, "type": "artist", "limit": limit},
            self._d.search, query, type="artist",
        )
        out = []
        for r in list(results)[:limit]:
            try:
                out.append({
                    "id": r.id,
                    "name": r.name,
                })
            except Exception:
                continue
        return out

    def search_master(self, query: str, limit: int = 5) -> list[dict]:
        """
        Hae master-releaseja. Master kokoaa kaikki painokset yhteen —
        parempi lähtökohta genre/style-tiedolle kuin yksittäinen release.
        """
        results = self._time(
            "database.search[master]", {"q": query, "type": "master", "limit": limit},
            self._d.search, query, type="master",
        )
        out = []
        for r in list(results)[:limit]:
            try:
                out.append({
                    "id": r.id,
                    "title": r.title,
                    "year": getattr(r, "year", None),
                    "genres": list(getattr(r, "genres", []) or []),
                    "styles": list(getattr(r, "styles", []) or []),
                })
            except Exception:
                continue
        return out

    # ─── Release ─────────────────────────────────────────────────────────────

    def release(self, release_id: int) -> ReleaseInfo:
        """
        Hae release ID:llä. Paras tapa saada tarkka genre/style-data.
        """
        r = self._time(
            "database.release", {"id": release_id},
            self._d.release, release_id,
        )
        artists = getattr(r, "artists", [])
        artist_name = artists[0].name if artists else "?"

        community = getattr(r, "community", None)
        rating = 0.0
        have = 0
        want = 0
        if community:
            rating_obj = getattr(community, "rating", None)
            if rating_obj:
                rating = float(getattr(rating_obj, "average", 0) or 0)
            have = int(getattr(community, "have", 0) or 0)
            want = int(getattr(community, "want", 0) or 0)

        tracklist = []
        for t in (getattr(r, "tracklist", []) or []):
            title = getattr(t, "title", "")
            if title:
                tracklist.append(title)

        return ReleaseInfo(
            id=r.id,
            title=r.title,
            artist=artist_name,
            year=getattr(r, "year", None),
            country=getattr(r, "country", "") or "",
            genres=list(getattr(r, "genres", []) or []),
            styles=list(getattr(r, "styles", []) or []),
            rating=rating,
            have=have,
            want=want,
            tracklist=tracklist,
        )

    def master(self, master_id: int) -> ReleaseInfo:
        """
        Hae master-release ID:llä.
        Sama rakenne kuin release(), mutta kokoaa kaikki painokset.
        """
        m = self._time(
            "database.master", {"id": master_id},
            self._d.master, master_id,
        )
        artists = getattr(m, "artists", [])
        artist_name = artists[0].name if artists else "?"

        tracklist = []
        for t in (getattr(m, "tracklist", []) or []):
            title = getattr(t, "title", "")
            if title:
                tracklist.append(title)

        return ReleaseInfo(
            id=m.id,
            title=m.title,
            artist=artist_name,
            year=getattr(m, "year", None),
            country="",
            genres=list(getattr(m, "genres", []) or []),
            styles=list(getattr(m, "styles", []) or []),
            rating=0.0,
            have=0,
            want=0,
            tracklist=tracklist,
        )

    # ─── Artisti ─────────────────────────────────────────────────────────────

    def artist(self, artist_id: int) -> dict:
        """
        Artistin perustiedot: nimi, profiili, aliakset.
        """
        a = self._time(
            "database.artist", {"id": artist_id},
            self._d.artist, artist_id,
        )
        return {
            "id": a.id,
            "name": a.name,
            "profile": getattr(a, "profile", "") or "",
            "aliases": [al.name for al in (getattr(a, "aliases", []) or [])],
            "urls": list(getattr(a, "urls", []) or []),
        }

    def artist_releases(
        self,
        artist_id: int,
        limit: int = 20,
        sort: str = "year",          # "year" | "title" | "format"
        sort_order: str = "desc",
    ) -> list[dict]:
        """
        Artistin julkaisut. Hyvä lähde genre/style-datalle — tyypillisesti
        master-releaseja joilla on genres/styles kenttä.
        Palauttaa: [{id, title, year, type, genres, styles}]
        """
        a = self._d.artist(artist_id)
        releases = self._time(
            "database.artist_releases",
            {"artist_id": artist_id, "limit": limit},
            a.releases.page, 1,
        )
        out = []
        for r in list(releases)[:limit]:
            try:
                out.append({
                    "id": r.id,
                    "title": r.title,
                    "year": getattr(r, "year", None),
                    "type": getattr(r, "type", ""),
                    "genres": list(getattr(r, "genres", []) or []),
                    "styles": list(getattr(r, "styles", []) or []),
                })
            except Exception:
                continue
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
                    **({"error": c.error} if c.error else {}),
                }
                for c in self.call_log
            ],
        }
