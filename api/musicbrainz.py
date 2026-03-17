"""
MusicBrainz API wrapper.

Mitä MusicBrainzista saadaan:
  search_recording   → hae kappaleita nimellä/artistilla → saa MBID:n
  search_artist      → hae artisteja → saa MBID:n
  recording          → kappaleen metatiedot, suhteet (covered-by, remix jne.)
  artist             → artistin tiedot, suhteet muihin artisteihin
  artist_recordings  → artistin kappaleet MBID:llä

Arvokkain data:
  - MBID (MusicBrainz ID) — globaali tunniste, yhdistää Last.fm/ListenBrainz dataan
  - artist relationships: "influenced by", "member of", "collaborated with"
  - recording relationships: "cover of", "remix of", "samples"
  - tags — yhteisön lisäämät genre/tyyli-tagit
  - release info: levymerkki, maa, vuosi

Ei API-avainta tarvita. User-Agent asetetaan automaattisesti.
Rate limit: 1 req/s (kirjasto hoitaa automaattisesti).
"""

import time
from dataclasses import dataclass, field

import musicbrainzngs

musicbrainzngs.set_useragent("SoittolistaPuristin", "0.1", "mokkatrukki@gmail.com")


# ─── Dataluokat ──────────────────────────────────────────────────────────────

@dataclass
class RecordingInfo:
    mbid: str
    title: str
    artist: str
    artist_mbid: str
    length_ms: int | None       # kappaleen kesto millisekunteina
    tags: list[str]             # yhteisötagit, lowercase
    release_year: int | None
    relationships: list[dict]   # cover of, remix of, samples jne.

    def __str__(self) -> str:
        mins = f"{self.length_ms // 60000}:{(self.length_ms % 60000) // 1000:02d}" if self.length_ms else "?"
        return f"{self.artist} — {self.title} [{mins}] mbid:{self.mbid[:8]}"


@dataclass
class ArtistInfo:
    mbid: str
    name: str
    type: str                   # "Person", "Group", "Orchestra" jne.
    country: str
    tags: list[str]
    begin_year: int | None
    end_year: int | None
    relationships: list[dict]   # influenced-by, member-of jne.


@dataclass
class ApiCall:
    endpoint: str
    params: dict
    result_count: int
    latency_ms: float
    error: str | None = None


# ─── Asiakas ─────────────────────────────────────────────────────────────────

class MusicBrainzClient:
    """
    MusicBrainz-wrapper musicbrainzngs:n päälle.
    Rate limit (1 req/s) hoidetaan kirjaston puolesta.
    """

    def __init__(self) -> None:
        self.call_log: list[ApiCall] = []

    def _call(self, endpoint: str, params: dict, fn, *args, **kwargs):
        t0 = time.monotonic()
        error = None
        result = None
        try:
            result = fn(*args, **kwargs)
        except musicbrainzngs.MusicBrainzError as e:
            error = str(e)
            raise
        finally:
            latency = (time.monotonic() - t0) * 1000
            count = 1
            if isinstance(result, dict):
                # Yritä arvata tulosten määrä vastauksen rakenteesta
                for key in ("recording-list", "artist-list", "release-list"):
                    if key in result:
                        count = len(result[key])
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

    def search_recording(
        self,
        title: str,
        artist: str = "",
        limit: int = 5,
    ) -> list[dict]:
        """
        Hae kappaleita nimellä ja optionaalisesti artistilla.
        Palauttaa: [{mbid, title, artist, artist_mbid, length_ms, score}]
        score = MusicBrainzin hakuosuvuus 0–100
        """
        kwargs: dict = {"recording": title, "limit": limit}
        if artist:
            kwargs["artist"] = artist

        raw = self._call(
            "recording.search",
            {"title": title, "artist": artist, "limit": limit},
            musicbrainzngs.search_recordings,
            **kwargs,
        )
        out = []
        for r in raw.get("recording-list", []):
            artist_credit = r.get("artist-credit", [])
            artist_name = ""
            artist_mbid = ""
            if artist_credit:
                ac = artist_credit[0]
                if isinstance(ac, dict) and "artist" in ac:
                    artist_name = ac["artist"].get("name", "")
                    artist_mbid = ac["artist"].get("id", "")

            length_ms = None
            raw_len = r.get("length")
            if raw_len:
                try:
                    length_ms = int(raw_len)
                except ValueError:
                    pass

            out.append({
                "mbid": r.get("id", ""),
                "title": r.get("title", ""),
                "artist": artist_name,
                "artist_mbid": artist_mbid,
                "length_ms": length_ms,
                "score": int(r.get("ext:score", 0)),
            })
        return out

    def search_artist(self, query: str, limit: int = 5) -> list[dict]:
        """
        Hae artisteja nimellä.
        Palauttaa: [{mbid, name, type, country, score}]
        """
        raw = self._call(
            "artist.search",
            {"artist": query, "limit": limit},
            musicbrainzngs.search_artists,
            artist=query,
            limit=limit,
        )
        out = []
        for a in raw.get("artist-list", []):
            out.append({
                "mbid": a.get("id", ""),
                "name": a.get("name", ""),
                "type": a.get("type", ""),
                "country": a.get("country", ""),
                "score": int(a.get("ext:score", 0)),
            })
        return out

    # ─── Recording ───────────────────────────────────────────────────────────

    def recording(self, mbid: str) -> RecordingInfo:
        """
        Hae kappaleen tiedot MBID:llä.
        Sisältää suhteet: cover of, remix of, samples, later version jne.
        """
        raw = self._call(
            "recording.get",
            {"mbid": mbid},
            musicbrainzngs.get_recording_by_id,
            mbid,
            includes=["artists", "tags", "releases", "recording-rels", "work-rels"],
        )
        r = raw.get("recording", {})

        artist_credit = r.get("artist-credit", [])
        artist_name = ""
        artist_mbid = ""
        if artist_credit:
            ac = artist_credit[0]
            if isinstance(ac, dict) and "artist" in ac:
                artist_name = ac["artist"].get("name", "")
                artist_mbid = ac["artist"].get("id", "")

        length_ms = None
        raw_len = r.get("length")
        if raw_len:
            try:
                length_ms = int(raw_len)
            except ValueError:
                pass

        tags = [t["name"].lower() for t in r.get("tag-list", [])]

        # Vuosi ensimmäisestä releasesta
        release_year = None
        releases = r.get("release-list", [])
        if releases:
            date = releases[0].get("date", "")
            if date and len(date) >= 4:
                try:
                    release_year = int(date[:4])
                except ValueError:
                    pass

        # Suhteet (cover of, remix of jne.)
        relationships = _parse_relationships(r.get("recording-relation-list", []))

        return RecordingInfo(
            mbid=r.get("id", mbid),
            title=r.get("title", ""),
            artist=artist_name,
            artist_mbid=artist_mbid,
            length_ms=length_ms,
            tags=tags,
            release_year=release_year,
            relationships=relationships,
        )

    # ─── Artist ──────────────────────────────────────────────────────────────

    def artist(self, mbid: str) -> ArtistInfo:
        """
        Artistin tiedot MBID:llä.
        Sisältää suhteet: influenced-by, member-of, collaborated-with jne.
        """
        raw = self._call(
            "artist.get",
            {"mbid": mbid},
            musicbrainzngs.get_artist_by_id,
            mbid,
            includes=["tags", "artist-rels"],
        )
        a = raw.get("artist", {})

        tags = [t["name"].lower() for t in a.get("tag-list", [])]

        begin_year = None
        end_year = None
        life = a.get("life-span", {})
        for key, target in [("begin", "begin_year"), ("end", "end_year")]:
            val = life.get(key, "")
            if val and len(val) >= 4:
                try:
                    if target == "begin_year":
                        begin_year = int(val[:4])
                    else:
                        end_year = int(val[:4])
                except ValueError:
                    pass

        relationships = _parse_relationships(a.get("artist-relation-list", []))

        return ArtistInfo(
            mbid=a.get("id", mbid),
            name=a.get("name", ""),
            type=a.get("type", ""),
            country=a.get("country", ""),
            tags=tags,
            begin_year=begin_year,
            end_year=end_year,
            relationships=relationships,
        )

    # ─── Tuottajaverkosto ─────────────────────────────────────────────────────

    def producer_graph(
        self,
        artist_name: str,
        max_recordings: int = 8,
    ) -> dict:
        """
        Tuottajaverkosto: etsi artisti → löydä tuottajat → löydä heidän muut tuotantonsa.

        Palauttaa:
        {
          "artist": "Arpa",
          "artist_mbid": "...",
          "producers": [
            {
              "name": "Väinö Karjalainen",
              "mbid": "...",
              "other_artists": ["Ursus Factory", "Nössö Nova", ...]
            }
          ]
        }

        Miten toimii:
          1. Hae artistin MBID
          2. Hae artistin kappaleet (artist_recordings)
          3. Per kappale: hae artist-rels → etsi "producer"-tyyppiset suhteet
          4. Per tuottaja: search_recordings(arid=tuottajan MBID) → poimii
             kaikki kappaleet joissa tuottaja on mukana (missä roolissa tahansa),
             ja kerää niiden artist-creditit = muut artistit joita tuottaja on tuottanut
        """
        # 1. Etsi artisti
        artists = self.search_artist(artist_name, limit=3)
        if not artists:
            return {"artist": artist_name, "producers": [], "error": "Artistia ei löydy"}

        artist_mbid = artists[0]["mbid"]
        artist_name_found = artists[0]["name"]

        # 2. Hae kappaleet
        recordings = self.artist_recordings(artist_mbid, limit=max_recordings)

        # 3. Etsi tuottajat artist-rels:stä
        producers: dict[str, str] = {}  # name → mbid
        for rec in recordings[:max_recordings]:
            try:
                rels = self._recording_artist_rels(rec["mbid"])
                for rel in rels:
                    if "producer" in rel["type"].lower() and rel["target_mbid"]:
                        producers[rel["target_name"]] = rel["target_mbid"]
            except Exception:
                continue

        if not producers:
            return {
                "artist": artist_name_found,
                "artist_mbid": artist_mbid,
                "producers": [],
                "note": "Ei tuottajatietoja MusicBrainzissa (kappaleet voivat puuttua tai olla merkitsemättä)",
            }

        # 4. Jokaiselle tuottajalle: hae muut artistit joita he ovat tuottaneet
        result_producers = []
        for producer_name, producer_mbid in producers.items():
            other_artists = self._productions_by_artist(
                producer_mbid,
                exclude_mbids={artist_mbid, producer_mbid},
            )
            result_producers.append({
                "name": producer_name,
                "mbid": producer_mbid,
                "other_artists": other_artists,
            })

        return {
            "artist": artist_name_found,
            "artist_mbid": artist_mbid,
            "producers": result_producers,
        }

    def _recording_artist_rels(self, recording_mbid: str) -> list[dict]:
        """Hae kappaleen artist-rels: tuottaja, äänittäjä, soittajat jne."""
        raw = self._call(
            "recording.artist_rels",
            {"mbid": recording_mbid},
            musicbrainzngs.get_recording_by_id,
            recording_mbid,
            includes=["artist-rels"],
        )
        r = raw.get("recording", {})
        return _parse_relationships(r.get("artist-relation-list", []))

    def _productions_by_artist(
        self,
        artist_mbid: str,
        exclude_mbids: set[str] | None = None,
        limit: int = 25,
    ) -> list[str]:
        """
        Hae artistit joita tämä henkilö on tuottanut (tai joiden kanssa on työskennellyt).

        Käyttää search_recordings(arid=mbid) — 'arid' on MusicBrainzin
        Lucene-kenttä joka löytää kappaleet joissa MBID esiintyy missä roolissa tahansa
        (myös tuottajana, ei vain pääartistina).
        Poimii näiden kappaleiden artist-creditit = muut artistit.
        """
        exclude_mbids = exclude_mbids or set()
        try:
            raw = self._call(
                "recording.search_by_producer",
                {"arid": artist_mbid, "limit": limit},
                musicbrainzngs.search_recordings,
                arid=artist_mbid,
                limit=limit,
            )
        except Exception:
            return []

        artists: dict[str, str] = {}  # mbid → name
        for r in raw.get("recording-list", []):
            for entry in r.get("artist-credit", []):
                if not isinstance(entry, dict) or "artist" not in entry:
                    continue
                a = entry["artist"]
                a_mbid = a.get("id", "")
                a_name = a.get("name", "")
                if a_mbid and a_mbid not in exclude_mbids:
                    artists[a_mbid] = a_name

        return list(artists.values())

    # ─── Artist recordings ────────────────────────────────────────────────────

    def artist_recordings(
        self,
        mbid: str,
        limit: int = 25,
    ) -> list[dict]:
        """
        Artistin kappaleet MBID:llä.
        Palauttaa: [{mbid, title, length_ms}]
        Huom: MusicBrainz palauttaa recordings per release — voi olla duplikaatteja.
        """
        raw = self._call(
            "artist.recordings",
            {"mbid": mbid, "limit": limit},
            musicbrainzngs.browse_recordings,
            artist=mbid,
            limit=limit,
        )
        out = []
        seen: set[str] = set()
        for r in raw.get("recording-list", []):
            rec_id = r.get("id", "")
            if rec_id in seen:
                continue
            seen.add(rec_id)

            length_ms = None
            raw_len = r.get("length")
            if raw_len:
                try:
                    length_ms = int(raw_len)
                except ValueError:
                    pass

            out.append({
                "mbid": rec_id,
                "title": r.get("title", ""),
                "length_ms": length_ms,
            })
            if len(out) >= limit:
                break
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


# ─── Apufunktiot ─────────────────────────────────────────────────────────────

def _parse_relationships(rel_list: list) -> list[dict]:
    """
    Muuntaa MusicBrainzin relationship-listan selkeäksi listaksi.
    [{type, direction, target_mbid, target_name, target_type}]
    """
    out = []
    for rel in rel_list:
        rel_type = rel.get("type", "")
        direction = rel.get("direction", "forward")

        # Kohde voi olla recording, artist, work...
        target_mbid = ""
        target_name = ""
        target_type = ""
        for key in ("recording", "artist", "work", "release"):
            if key in rel:
                obj = rel[key]
                target_mbid = obj.get("id", "")
                target_name = obj.get("name", obj.get("title", ""))
                target_type = key
                break

        out.append({
            "type": rel_type,
            "direction": direction,
            "target_type": target_type,
            "target_mbid": target_mbid,
            "target_name": target_name,
        })
    return out
