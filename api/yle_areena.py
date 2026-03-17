"""
YLE Areena -scraper.

Hakee musiikkiohjelmien kappallistat Areenan jaksojen kuvauksista.
Ei vaadi API-avainta — käyttää julkista app_id:tä.

Logiikka:
  1. list_shows()          → tunnetut musiikkiohjelmat (sarja-ID → nimi)
  2. show_episodes()       → sarjan viimeisimmät jaksot
  3. episode_tracks()      → jakson kappalelista kuvauksen parsinnasta
  4. latest_tracks()       → lyhin reitti: sarja → uusin jakso → kappaleet

Kuvausten parsinta tukee kolmea formaattia:
  - "BIISILISTA:\\n Artisti - Kappale"   (Anne Lainto, YleX Vaihtoehto)
  - "Artisti - Kappale" rivit ilman otsikkoa (Menomesta)
  - "Artisti: Kappale"                   (Kissankehto, Sekahaku, klassinen)

Ohjelmalistaus: https://areena.yle.fi/podcastit/ohjelmat/57-bNBwRNd2D
"""

import base64
import json
import re
import time
from dataclasses import dataclass, field

import httpx


AREENA_API = "https://areena.api.yle.fi/v1/ui"
AREENA_PARAMS = {
    "language": "fi",
    "v": "10",
    "client": "yle-areena-web",
    "app_id": "areena-web-items",
    "app_key": "wlTs5D9OjIdeS9krPzRQR4I1PYVzoazN",
}

# Tunnetut musiikkiohjelmat — sarja-ID → nimi
# Löydät lisää: https://areena.yle.fi/podcastit/ohjelmat/57-bNBwRNd2D
MUSIC_SHOWS: dict[str, str] = {
    "1-1653834": "Levylautakunta",
    "1-3201240": "Pekka Laineen Ihmemaa",
    "1-3262577": "Kissankehto - Susanna Vainiola",
    "1-3210491": "Tuuli Saksalan keidas",
    "1-75855232": "Sillanpään sunnuntai",
    "1-64590159": "Radio Suomen Musiikki-ilta",
    "1-4409832": "Iskelmäradio",
    "1-1479287": "Entisten nuorten sävellahja",
    "1-51013437": "Anne Lainto <3 Rock",
    "1-71115455": "YleX Vaihtoehto: Raine Laaksonen",
    "1-72923904": "Menomesta",
    "1-2069638": "Sekahaku",
    "1-4658788": "Toni Laaksosen Lauantaitanssit",
    "1-4391300": "YleX Throwback: Womma Seppälä",
    "1-1301952": "Yöradio - toiveiden yö",
    "1-2120710": "Jazzklubi",
    "1-50432696": "Epäilyttävän uutta - Aki Yli-Salomäki",
    "1-1622504": "Lauantain toivotut levyt",
    "1-4591832": "Keinuva talo - Mika Kauhanen",
}


# ─── Dataluokat ──────────────────────────────────────────────────────────────

@dataclass
class Track:
    artist: str
    title: str

    def __str__(self) -> str:
        return f"{self.artist} — {self.title}"


@dataclass
class Episode:
    id: str
    title: str
    date: str
    url: str
    tracks: list[Track] = field(default_factory=list)


@dataclass
class ApiCall:
    endpoint: str
    params: dict
    result_count: int
    latency_ms: float
    error: str | None = None


# ─── Asiakas ─────────────────────────────────────────────────────────────────

class YleAreenaClient:

    def __init__(self) -> None:
        self.call_log: list[ApiCall] = []

    def _get(self, path: str, extra: dict | None = None) -> dict:
        params = {**AREENA_PARAMS, **(extra or {})}
        url = f"{AREENA_API}{path}"
        t0 = time.monotonic()
        error = None
        result = None
        try:
            with httpx.Client() as client:
                resp = client.get(url, params=params, timeout=10)
                resp.raise_for_status()
                result = resp.json()
        except Exception as e:
            error = str(e)
            raise
        finally:
            latency = (time.monotonic() - t0) * 1000
            self.call_log.append(ApiCall(
                endpoint=path,
                params={**params, **(extra or {})},
                result_count=1,
                latency_ms=round(latency, 1),
                error=error,
            ))
        return result

    # ─── Ohjelmat ────────────────────────────────────────────────────────────

    def discover_shows(self) -> list[dict]:
        """
        Hakee kaikki musiikkiohjelmat Areenan musiikin kategorisivulta ja
        testaa mitkä niistä oikeasti palauttavat kappalelistan.
        Palauttaa: [{id, name, track_count, sample}] — vain ne joissa on kappaleita.

        Hyödyllinen kun haluat löytää uusia ohjelmia MUSIC_SHOWS-listaan.
        Tekee paljon API-kutsuja — käytä harvoin.
        """
        import re as _re, base64 as _b64

        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        PARAMS = {
            "language": "fi", "v": "10", "client": "yle-areena-web",
            "app_id": "areena-web-items", "app_key": "wlTs5D9OjIdeS9krPzRQR4I1PYVzoazN",
        }

        # 1) Hae musiikin kategoriasivu
        with httpx.Client(follow_redirects=True) as c:
            resp = c.get(
                "https://areena.yle.fi/podcastit/ohjelmat/57-bNBwRNd2D",
                headers=headers, timeout=15,
            )
            html = resp.text

        import json as _json
        m = _re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, _re.DOTALL)
        if not m:
            return []
        page_data = _json.loads(m.group(1))

        # 2) Kerää content/list URI:t
        content_uris: list[str] = []
        def _find_uris(obj):
            if isinstance(obj, dict):
                uri = obj.get("uri", "")
                if "content/list" in uri and "token=" in uri:
                    content_uris.append(uri)
                for v in obj.values():
                    _find_uris(v)
            elif isinstance(obj, list):
                for item in obj:
                    _find_uris(item)
        _find_uris(page_data)

        # 3) Hae kaikki sarjat, deduploi nimellä
        name_to_id: dict[str, str] = {}
        with httpx.Client(follow_redirects=True) as c:
            for uri in content_uris:
                t = _re.search(r"token=(eyJ[^&]+)", uri)
                if not t:
                    continue
                try:
                    resp2 = c.get(
                        "https://areena.api.yle.fi/v1/ui/content/list",
                        params={**PARAMS, "token": t.group(1), "crop": "100"},
                        headers=headers, timeout=8,
                    )
                    if resp2.status_code != 200:
                        continue
                    cards = resp2.json().get("data", {})
                    if isinstance(cards, dict):
                        cards = cards.get("cards", [])
                    if not isinstance(cards, list):
                        continue
                    for card in cards:
                        sid = next(
                            (lbl["raw"] for lbl in card.get("labels", []) if lbl.get("type") == "itemId"),
                            "",
                        )
                        name = card.get("title", "")
                        if sid and name and name not in name_to_id:
                            name_to_id[name] = sid
                except Exception:
                    continue

        # 4) Testaa mitkä palauttavat kappaleita (ohita jo tunnetut)
        known_ids = set(MUSIC_SHOWS.keys())
        results = []
        for name, sid in name_to_id.items():
            if sid in known_ids:
                continue
            try:
                ep = self.latest_tracks(sid)
                if ep.tracks and len(ep.tracks) >= 3:
                    results.append({
                        "id": sid,
                        "name": name,
                        "track_count": len(ep.tracks),
                        "sample": str(ep.tracks[0]),
                    })
            except Exception:
                continue

        return sorted(results, key=lambda x: -x["track_count"])

    def list_shows(self) -> list[dict]:
        """Listaa tunnetut musiikkiohjelmat."""
        return [{"id": sid, "name": name} for sid, name in MUSIC_SHOWS.items()]

    def show_episodes(self, series_id: str, limit: int = 5) -> list[Episode]:
        """
        Hakee sarjan viimeisimmät jaksot.
        Palauttaa: [Episode(id, title, date, url)]
        """
        episode_ids = self._get_episode_ids(series_id, limit=limit)
        episodes = []
        for eid in episode_ids:
            try:
                data = self._get(f"/items/{eid}.json")
                card = (data.get("data", {}).get("cards") or [{}])[0]
                date = next(
                    (
                        lbl["formatted"]
                        for lbl in card.get("labels", [])
                        if lbl.get("type") == "generic" and "." in lbl.get("formatted", "")
                    ),
                    "",
                )
                episodes.append(Episode(
                    id=eid,
                    title=card.get("title", ""),
                    date=date,
                    url=f"https://areena.yle.fi/{eid}",
                ))
            except Exception:
                continue
        return episodes

    def episode_tracks(self, episode_id: str) -> Episode:
        """
        Hae jakson kappalelista kuvauksesta.
        Palauttaa Episode jossa tracks-lista.
        """
        data = self._get(f"/items/{episode_id}.json")
        d = data.get("data", {})
        card = (d.get("cards") or [{}])[0]
        description = card.get("description", "")
        date = next(
            (
                lbl["formatted"]
                for lbl in card.get("labels", [])
                if lbl.get("type") == "generic" and "." in lbl.get("formatted", "")
            ),
            "",
        )
        raw_tracks = _parse_tracks(description)
        tracks = [Track(artist=t["artist"], title=t["title"]) for t in raw_tracks]
        return Episode(
            id=episode_id,
            title=card.get("title", ""),
            date=date,
            url=f"https://areena.yle.fi/{episode_id}",
            tracks=tracks,
        )

    def latest_tracks(self, series_id: str) -> Episode:
        """
        Lyhin reitti: sarja → uusin jakso → kappaleet.
        """
        ids = self._get_episode_ids(series_id, limit=1)
        if not ids:
            return Episode(id="", title="", date="", url="")
        return self.episode_tracks(ids[0])

    # ─── Sisäiset ────────────────────────────────────────────────────────────

    def _get_episode_ids(self, series_id: str, limit: int = 5) -> list[str]:
        """
        Hakee sarjan viimeisimmät episodi-ID:t JWT+content/list-APIa käyttäen.
        Sama logiikka kuin soittolista-suosittelija/mcp_servers/music_discovery_mcp.py
        """
        page_url = f"https://areena.yle.fi/{series_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
        }
        t0 = time.monotonic()
        error = None
        result: list[str] = []
        try:
            with httpx.Client(follow_redirects=True) as client:
                # 1) Hae HTML → ota JWT-token episodeille
                page_resp = client.get(page_url, headers=headers, timeout=15)
                page_resp.raise_for_status()
                html = page_resp.text
                cookie_hdr = "; ".join(
                    f"{n}={v}" for n, v in client.cookies.items()
                )

                # 2) Poimi JWT jossa cardOptionsTemplate=episodes + availability=current
                tokens = re.findall(
                    r"content/list\?token=(eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)",
                    html,
                )
                ep_token = None
                for t in tokens:
                    try:
                        payload = json.loads(
                            base64.urlsafe_b64decode(t.split(".")[1] + "==")
                        )
                        if (
                            "episodes" in payload.get("cardOptionsTemplate", "")
                            and "current" in payload.get("source", "")
                        ):
                            ep_token = t
                            break
                    except Exception:
                        continue

                if not ep_token:
                    return []

                # 3) Kutsu content/list-API tokenilla
                api_url = (
                    f"https://areena.api.yle.fi/v1/ui/content/list?token={ep_token}"
                    f"&language=fi&v=10&client=yle-areena-web"
                    f"&app_id=areena-web-items&app_key=wlTs5D9OjIdeS9krPzRQR4I1PYVzoazN"
                    f"&limit={limit}"
                )
                req_headers = {**headers, "Cookie": cookie_hdr} if cookie_hdr else headers
                api_resp = client.get(api_url, headers=req_headers, timeout=10)
                api_resp.raise_for_status()
                api_data = api_resp.json()

            # 4) Kerää episodi-ID:t cardeista
            seen: set[str] = set()
            cards = api_data.get("data", {})
            if isinstance(cards, dict):
                cards = cards.get("cards", [])
            if not isinstance(cards, list):
                cards = []
            for card in cards:
                for label in card.get("labels", []):
                    if label.get("type") == "itemId":
                        eid = label.get("raw", "")
                        if eid and eid != series_id and eid not in seen:
                            seen.add(eid)
                            result.append(eid)

            # Fallback: poimi kaikki 1-XXXXXXX ID:t JSON:sta
            if not result:
                for eid in re.findall(r"1-\d{7,}", json.dumps(api_data)):
                    if eid != series_id and eid not in seen:
                        seen.add(eid)
                        result.append(eid)

            result = result[:limit]

        except Exception as e:
            error = str(e)
        finally:
            latency = (time.monotonic() - t0) * 1000
            self.call_log.append(ApiCall(
                endpoint=f"areena.episodes/{series_id}",
                params={"series_id": series_id, "limit": limit},
                result_count=len(result),
                latency_ms=round(latency, 1),
                error=error,
            ))

        return result

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


# ─── Parsinta ────────────────────────────────────────────────────────────────

def _parse_tracks(description: str) -> list[dict]:
    """
    Parsii kappalelistan jakson kuvauksesta.
    Tukee kolmea formaattia:
      - "BIISILISTA:\\n Artisti - Kappale"   (Anne Lainto, YleX Vaihtoehto)
      - "Artisti - Kappale" rivit ilman otsikkoa (Menomesta, ≥5 riviä)
      - "Artisti: Kappale"                   (Kissankehto, Sekahaku, klassinen)
    """
    tracks = []

    # Moodi 1: BIISILISTA / Soittolista -otsikon jälkeen Artisti - Kappale
    biisilista_m = re.search(
        r"(?:BIISILISTA|Biisilista|Soittolista|SOITTOLISTA)\s*:?\s*\n",
        description,
    )
    if biisilista_m:
        section = description[biisilista_m.end():]
        for line in section.splitlines():
            line = line.strip()
            if not line or " - " not in line:
                continue
            line = re.sub(r"^\d+\.\s*", "", line)
            parts = line.split(" - ", 1)
            if len(parts) != 2:
                continue
            artist, title = parts[0].strip(), parts[1].strip()
            title = re.sub(r"\s*/\s*\S.*$", "", title).strip()
            if artist and title and len(artist) < 80:
                tracks.append({"artist": artist, "title": title})
        return tracks

    # Moodi 2: pelkät "Artisti - Kappale" -rivit ilman otsikkoa (≥5 riviä → tunnistetaan listaksi)
    dash_lines = [
        line.strip()
        for line in description.splitlines()
        if " - " in line.strip()
        and not re.match(r"^klo\s", line.strip(), re.I)
        and len(line.strip()) > 5
    ]
    if len(dash_lines) >= 5:
        for line in dash_lines:
            parts = line.split(" - ", 1)
            artist, title = parts[0].strip(), parts[1].strip()
            title = re.sub(r"\s*/\s*\S.*$", "", title).strip()
            if artist and title and len(artist) < 80:
                tracks.append({"artist": artist, "title": title})
        return tracks

    # Moodi 3: "Artisti: Kappale" tai "N. Artisti: Kappale"
    for line in description.splitlines():
        line = line.strip()
        if ":" in line and len(line) > 5:
            parts = line.split(":", 1)
            artist = parts[0].strip()
            title = parts[1].strip()
            artist = re.sub(r"^\d+\.\s*", "", artist).strip()
            title = re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip()
            title = re.sub(r"\s*\([^)]{0,60}\)\s*$", "", title).strip()
            title = title.split("\t")[0].strip()
            if artist and title and len(artist) < 80 and not artist.lower().startswith("ohjelma"):
                tracks.append({"artist": artist, "title": title})

    return tracks
