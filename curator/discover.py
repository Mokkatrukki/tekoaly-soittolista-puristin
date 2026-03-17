"""
curator/discover.py — Rinnakkainen discovery-moottori.

Käyttö:
    from curator.discover import DiscoveryEngine
    engine = DiscoveryEngine()

    # Hae laajasti — Last.fm + Discogs rinnakkain
    results = engine.expand_artists(["Fishmans", "Pizzicato Five"], depth=2)
    results = engine.tag_universe(["city pop", "shibuya-kei"])

Arkkitehtuuri:
- ThreadPoolExecutor hoitaa rinnakkaisuuden
- Last.fm + Discogs ajetaan samanaikaisesti per artisti
- Tulokset yhdistetään ja pisteytetään: want-arvo + match-score
- Deduplikaatio normalisoinnilla
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable

from api.lastfm import LastFmClient, SimilarArtist
from api.discogs import DiscogsClient


# ─── Dataluokat ──────────────────────────────────────────────────────────────

@dataclass
class ArtistCandidate:
    name: str
    lastfm_score: float = 0.0   # summa match-arvoista similar_artists-verkossa
    discogs_want: int = 0        # paras want-arvo Discogsin löydöistä
    discogs_styles: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)  # mistä löytyi

    @property
    def combined_score(self) -> float:
        want_score = min(self.discogs_want / 1000, 5.0)  # 0–5 pistettä wantista
        return self.lastfm_score + want_score

    def __str__(self) -> str:
        styles = ", ".join(self.discogs_styles[:3])
        return (
            f"{self.name}: score={self.combined_score:.2f} "
            f"(lastfm={self.lastfm_score:.2f}, want={self.discogs_want}) "
            f"| {styles}"
        )


# ─── Moottori ─────────────────────────────────────────────────────────────────

class DiscoveryEngine:
    """
    Rinnakkainen discovery-moottori Last.fm + Discogs.

    Kaikki haut ajetaan ThreadPoolExecutorilla — Last.fm ja Discogs
    vastaavat samanaikaisesti, ei peräkkäin.
    """

    def __init__(
        self,
        lfm: LastFmClient | None = None,
        dc: DiscogsClient | None = None,
        max_workers: int = 4,
    ) -> None:
        self.lfm = lfm or LastFmClient()
        self.dc = dc or DiscogsClient()
        self._workers = max_workers

    # ─── Ydin: rinnakkainen haku ─────────────────────────────────────────────

    def _parallel(self, tasks: list[tuple[Callable, tuple, dict]]) -> list:
        """
        Aja lista (fn, args, kwargs) -tehtäviä rinnakkain.
        Palauttaa tulokset listana (None jos epäonnistui).
        """
        results = [None] * len(tasks)
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            futures = {
                pool.submit(fn, *args, **kwargs): i
                for i, (fn, args, kwargs) in enumerate(tasks)
            }
            for future in as_completed(futures):
                i = futures[future]
                try:
                    results[i] = future.result()
                except Exception as e:
                    results[i] = None
        return results

    # ─── Last.fm-haut ────────────────────────────────────────────────────────

    def similar_network(
        self,
        seeds: list[str],
        depth: int = 2,
        limit_per_seed: int = 10,
        exclude: set[str] | None = None,
    ) -> dict[str, float]:
        """
        Rakenna similar_artists-verkko annetuista siemenistä.
        depth=1: similar(seeds)
        depth=2: similar(seeds) + similar(tier2)

        Palauttaa: {artist_name: kumulatiivinen_match_score}
        """
        exclude = {a.lower() for a in (exclude or [])}
        scores: dict[str, float] = {}

        def _fetch_similar(artist: str, weight: float) -> list[tuple[str, float]]:
            try:
                sims = self.lfm.similar_artists(artist, limit=limit_per_seed)
                return [(s.name, s.match * weight) for s in sims]
            except Exception:
                return []

        # Tier 1
        tier1_tasks = [
            (_fetch_similar, (seed, 1.0), {})
            for seed in seeds
        ]
        tier1_results = self._parallel(tier1_tasks)

        tier2_seeds = []
        for pairs in tier1_results:
            if not pairs:
                continue
            for name, score in pairs:
                if name.lower() not in exclude:
                    scores[name] = scores.get(name, 0) + score
                    tier2_seeds.append((name, score))

        if depth < 2:
            return scores

        # Tier 2 — top-N tier1-artisteista
        tier2_seeds.sort(key=lambda x: -x[1])
        tier2_top = [name for name, _ in tier2_seeds[:20]]

        tier2_tasks = [
            (_fetch_similar, (seed, 0.5), {})
            for seed in tier2_top
        ]
        tier2_results = self._parallel(tier2_tasks)

        for pairs in tier2_results:
            if not pairs:
                continue
            for name, score in pairs:
                if name.lower() not in exclude:
                    scores[name] = scores.get(name, 0) + score

        return scores

    def tag_universe(
        self,
        tags: list[str],
        limit_per_tag: int = 20,
        exclude: set[str] | None = None,
    ) -> dict[str, float]:
        """
        Hae top-artistit usealta tagilta rinnakkain.
        Palauttaa: {artist_name: rank_score}
        """
        exclude = {a.lower() for a in (exclude or [])}

        def _fetch_tag(tag: str) -> list[dict]:
            try:
                return self.lfm.tag_top_artists(tag, limit=limit_per_tag)
            except Exception:
                return []

        tasks = [(_fetch_tag, (tag,), {}) for tag in tags]
        results = self._parallel(tasks)

        scores: dict[str, float] = {}
        for artists in results:
            if not artists:
                continue
            for a in artists:
                name = a["name"]
                if name.lower() not in exclude:
                    rank = a.get("rank", 0) or 0
                    score = max(1.0, limit_per_tag - rank) / limit_per_tag
                    scores[name] = scores.get(name, 0) + score

        return scores

    # ─── Discogs-validointi ──────────────────────────────────────────────────

    def discogs_validate(
        self,
        artist_names: list[str],
        country: str = "Japan",
    ) -> dict[str, tuple[int, list[str]]]:
        """
        Hae Discogs want-arvo + styles kaikille artisteille.
        Ajetaan sarjassa (ei rinnakkain) — Discogs rate limit 1 req/s.
        Palauttaa: {artist_name: (want, [styles])}
        """
        out: dict[str, tuple[int, list[str]]] = {}
        for name in artist_names:
            try:
                results = self.dc.search_japan(name, limit=3) if country == "Japan" \
                    else self.dc.search_release(name, limit=3)
                if results:
                    best = max(results, key=lambda r: r.get("community_want", 0))
                    out[name] = (
                        best.get("community_want", 0),
                        best.get("styles", [])[:4],
                    )
                else:
                    out[name] = (0, [])
            except Exception:
                out[name] = (0, [])
        return out

    # ─── Yhdistetty ─────────────────────────────────────────────────────────

    def expand_artists(
        self,
        seeds: list[str],
        tags: list[str] | None = None,
        depth: int = 2,
        limit: int = 20,
        exclude: set[str] | None = None,
        country: str = "Japan",
    ) -> list[ArtistCandidate]:
        """
        Täysinen discovery-putki:
        1. Last.fm similar_artists -verkko (depth-tasot) — rinnakkain
        2. Last.fm tag_top_artists (valinnaiset tagit) — rinnakkain
        3. Discogs want-validointi — rinnakkain

        Palauttaa: [ArtistCandidate] järjestettynä combined_score mukaan.
        """
        exclude = {a.lower() for a in (exclude or [])}

        # Last.fm-haut rinnakkain
        print(f"  [discover] Last.fm similar_network ({len(seeds)} siementä, depth={depth})...")
        t0 = time.monotonic()
        network_scores = self.similar_network(seeds, depth=depth, exclude=exclude)

        tag_scores: dict[str, float] = {}
        if tags:
            print(f"  [discover] Last.fm tag_universe ({len(tags)} tägiä)...")
            tag_scores = self.tag_universe(tags, exclude=exclude)

        # Yhdistä kandidaatit
        all_names = set(network_scores) | set(tag_scores)
        all_names -= {a.lower() for a in exclude}
        # Suodata pois jotka ovat excludessa (case-insensitive)
        all_names = {n for n in all_names if n.lower() not in exclude}

        print(f"  [discover] {len(all_names)} kandidaattia, Discogs-validointi...")
        # Rajoita validointi top-N kandidaatteihin Last.fm-pisteiden mukaan
        ranked_by_lastfm = sorted(
            all_names,
            key=lambda n: network_scores.get(n, 0) + tag_scores.get(n, 0),
            reverse=True,
        )
        to_validate = ranked_by_lastfm[:min(50, len(ranked_by_lastfm))]

        # Rajoita Discogs-validointi top-30:een — rate limit tekee enemmästä hidasta
        to_validate = to_validate[:30]
        dc_data = self.discogs_validate(to_validate, country=country)
        elapsed = time.monotonic() - t0
        print(f"  [discover] valmis {elapsed:.1f}s")

        candidates = []
        for name in to_validate:
            lfm_score = network_scores.get(name, 0) + tag_scores.get(name, 0)
            want, styles = dc_data.get(name, (0, []))
            sources = []
            if name in network_scores:
                sources.append("lastfm_similar")
            if name in tag_scores:
                sources.append("lastfm_tag")

            candidates.append(ArtistCandidate(
                name=name,
                lastfm_score=lfm_score,
                discogs_want=want,
                discogs_styles=styles,
                sources=sources,
            ))

        candidates.sort(key=lambda c: -c.combined_score)
        return candidates[:limit]


# ─── Nopea CLI-ajuri ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Discovery-moottori")
    parser.add_argument("seeds", nargs="+", help="Siemenartistit")
    parser.add_argument("--tags", nargs="*", default=[], help="Last.fm-tagit")
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--exclude", nargs="*", default=[])
    args = parser.parse_args()

    engine = DiscoveryEngine()
    results = engine.expand_artists(
        seeds=args.seeds,
        tags=args.tags or None,
        depth=args.depth,
        limit=args.limit,
        exclude=set(args.exclude),
    )

    print(f"\n{'='*60}")
    print(f"Top {len(results)} löydöt:")
    print(f"{'='*60}")
    for c in results:
        print(f"  {c}")
