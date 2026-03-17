"""
Suomen IFPI-listatiedot 2000–2025.

Data: data/ifpi_charts.db (155 000 riviä)
  chart_type: "singlet" | "albumit" | "radio"
  Kentät: chart_type, year, week, position, artist, title, label, weeks_on_chart

Käyttötarkoitukset:
  - top_tracks_by_year   → suosituimmat kappaleet vuodelta/aikaväliltä
  - artist_chart_history → onko artisti ollut listalla, kuinka menestynyt
  - search_charts        → hae artisti/kappale nimellä listadatasta
  - top_artists_by_era   → suosituimmat artistit aikakaudella

Ei API-kutsuja — kaikki data on paikallisessa SQLite-tietokannassa.
"""

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "ifpi_charts.db"


# ─── Dataluokat ──────────────────────────────────────────────────────────────

@dataclass
class ChartEntry:
    chart_type: str     # "singlet" | "albumit" | "radio"
    year: int
    week: int
    position: int
    artist: str
    title: str
    label: str
    weeks_on_chart: int

    def __str__(self) -> str:
        return f"#{self.position} {self.artist} — {self.title} ({self.year} vk{self.week})"


# ─── Asiakas ─────────────────────────────────────────────────────────────────

class FinnishChartsClient:
    """
    Paikallinen haku IFPI Suomi -listatietokantaan.
    Ei verkkoyhteyttä — kaikki kyselyt SQLite:hen.
    """

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self._db = str(db_path)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db)
        conn.row_factory = sqlite3.Row
        return conn

    # ─── Haku ────────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        chart_type: str = "",    # "" = kaikki, "singlet" | "albumit" | "radio"
        year_from: int = 2000,
        year_to: int = 2025,
        limit: int = 20,
    ) -> list[ChartEntry]:
        """
        Hae artistia tai kappaletta nimellä.
        Palauttaa parhaat osuvat, suosituimmat ensin (min position).
        """
        q = query.lower()
        params: list = [f"%{q}%", f"%{q}%", year_from, year_to]
        type_clause = ""
        if chart_type:
            type_clause = "AND chart_type = ?"
            params.append(chart_type)

        sql = f"""
            SELECT chart_type, year, week, position, artist, title, label, weeks_on_chart
            FROM chart_entries
            WHERE (LOWER(artist) LIKE ? OR LOWER(title) LIKE ?)
              AND year BETWEEN ? AND ?
              {type_clause}
            ORDER BY position ASC, weeks_on_chart DESC
            LIMIT ?
        """
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [_row_to_entry(r) for r in rows]

    def top_tracks(
        self,
        chart_type: str = "singlet",
        year_from: int = 2000,
        year_to: int = 2025,
        limit: int = 30,
    ) -> list[dict]:
        """
        Suosituimmat kappaleet aikavälillä — pisteytetty sijalla ja viikkojen määrällä.
        Palauttaa: [{artist, title, score, peak_position, total_weeks, years}]
        score = sum(21 - position) per viikko (sija 1 = 20 pistettä/vko)
        """
        sql = """
            SELECT artist, title,
                   SUM(MAX(0, 21 - position)) AS score,
                   MIN(position) AS peak_position,
                   COUNT(*) AS weeks,
                   MIN(year) AS first_year,
                   MAX(year) AS last_year
            FROM chart_entries
            WHERE chart_type = ?
              AND year BETWEEN ? AND ?
            GROUP BY LOWER(artist), LOWER(title)
            ORDER BY score DESC
            LIMIT ?
        """
        with self._conn() as conn:
            rows = conn.execute(sql, [chart_type, year_from, year_to, limit]).fetchall()

        return [
            {
                "artist": r["artist"],
                "title": r["title"],
                "score": r["score"],
                "peak_position": r["peak_position"],
                "total_weeks": r["weeks"],
                "years": f"{r['first_year']}–{r['last_year']}" if r["first_year"] != r["last_year"] else str(r["first_year"]),
            }
            for r in rows
        ]

    def top_artists(
        self,
        chart_type: str = "singlet",
        year_from: int = 2000,
        year_to: int = 2025,
        limit: int = 20,
    ) -> list[dict]:
        """
        Suosituimmat artistit aikavälillä.
        Palauttaa: [{artist, score, peak_position, chart_entries, years}]
        """
        sql = """
            SELECT artist,
                   SUM(MAX(0, 21 - position)) AS score,
                   MIN(position) AS peak_position,
                   COUNT(DISTINCT title) AS unique_titles,
                   COUNT(*) AS total_weeks,
                   MIN(year) AS first_year,
                   MAX(year) AS last_year
            FROM chart_entries
            WHERE chart_type = ?
              AND year BETWEEN ? AND ?
            GROUP BY LOWER(artist)
            ORDER BY score DESC
            LIMIT ?
        """
        with self._conn() as conn:
            rows = conn.execute(sql, [chart_type, year_from, year_to, limit]).fetchall()

        return [
            {
                "artist": r["artist"],
                "score": r["score"],
                "peak_position": r["peak_position"],
                "unique_titles": r["unique_titles"],
                "total_weeks": r["total_weeks"],
                "years": f"{r['first_year']}–{r['last_year']}" if r["first_year"] != r["last_year"] else str(r["first_year"]),
            }
            for r in rows
        ]

    def artist_history(
        self,
        artist: str,
        chart_type: str = "",
    ) -> dict:
        """
        Artistin koko listahistoria: kaikki kappaleet, paras sija, yhteispistemäärä.
        Palauttaa: {artist, total_weeks, peak_position, score, tracks: [{title, peak, weeks, years}]}
        """
        params: list = [f"%{artist.lower()}%"]
        type_clause = ""
        if chart_type:
            type_clause = "AND chart_type = ?"
            params.append(chart_type)

        sql = f"""
            SELECT artist, title, chart_type,
                   MIN(position) AS peak,
                   COUNT(*) AS weeks,
                   SUM(MAX(0, 21 - position)) AS score,
                   MIN(year) AS first_year,
                   MAX(year) AS last_year
            FROM chart_entries
            WHERE LOWER(artist) LIKE ?
              {type_clause}
            GROUP BY LOWER(title), chart_type
            ORDER BY score DESC
        """
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()

        if not rows:
            return {"artist": artist, "found": False}

        tracks = [
            {
                "title": r["title"],
                "chart_type": r["chart_type"],
                "peak_position": r["peak"],
                "total_weeks": r["weeks"],
                "years": f"{r['first_year']}–{r['last_year']}" if r["first_year"] != r["last_year"] else str(r["first_year"]),
            }
            for r in rows
        ]
        return {
            "artist": rows[0]["artist"] if rows else artist,  # type: ignore[index]
            "found": True,
            "total_weeks": sum(t["total_weeks"] for t in tracks),
            "peak_position": min(t["peak_position"] for t in tracks),
            "total_score": sum(r["score"] for r in rows),
            "tracks": tracks,
        }

    def weekly_chart(
        self,
        year: int,
        week: int,
        chart_type: str = "singlet",
    ) -> list[ChartEntry]:
        """Tietyn viikon lista."""
        sql = """
            SELECT chart_type, year, week, position, artist, title, label, weeks_on_chart
            FROM chart_entries
            WHERE chart_type = ? AND year = ? AND week = ?
            ORDER BY position
        """
        with self._conn() as conn:
            rows = conn.execute(sql, [chart_type, year, week]).fetchall()
        return [_row_to_entry(r) for r in rows]

    def available_weeks(self, chart_type: str = "singlet") -> list[tuple[int, int]]:
        """Palauttaa kaikki saatavilla olevat (year, week) -parit."""
        sql = "SELECT year, week FROM scraped_weeks WHERE chart_type = ? ORDER BY year, week"
        with self._conn() as conn:
            rows = conn.execute(sql, [chart_type]).fetchall()
        return [(r["year"], r["week"]) for r in rows]


# ─── Apufunktiot ─────────────────────────────────────────────────────────────

def _row_to_entry(r: sqlite3.Row) -> ChartEntry:
    return ChartEntry(
        chart_type=r["chart_type"],
        year=r["year"],
        week=r["week"],
        position=r["position"],
        artist=r["artist"],
        title=r["title"],
        label=r["label"] or "",
        weeks_on_chart=r["weeks_on_chart"] or 0,
    )
