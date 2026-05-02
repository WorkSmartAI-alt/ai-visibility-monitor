"""avm threads — surface high-leverage community threads from citation history."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from avm.surfaces import categorize_url, SURFACE_PARENTS, _build_categories

# All community leaf categories
_COMMUNITY_LEAVES: set[str] = set(SURFACE_PARENTS.get("community", []))


def _load_run(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [threads] skipping {path.name}: {e}", file=sys.stderr)
        return None


def _is_community(url: str, surface_filter: list[str] | None, cats: dict) -> bool:
    cat = categorize_url(url, cats)
    if surface_filter:
        return cat in surface_filter
    return cat in _COMMUNITY_LEAVES


def find_top_threads(
    data_dir: Path,
    surface_filter: list[str] | None = None,
    min_query_count: int = 1,
    top_n: int = 20,
) -> list[dict]:
    """
    Scan all citations-*.json files, dedup community URLs, rank by:
    1. Number of distinct queries that cited the URL
    2. Number of distinct engines that cited the URL
    3. Recency (most recent run date wins ties)

    Returns ranked list of thread dicts.
    """
    files = sorted(data_dir.glob("citations-20*.json"))
    files = [f for f in files if "-latest" not in f.stem]

    cats = _build_categories()

    # url → aggregated data
    url_data: dict[str, dict] = {}

    for f in files:
        data = _load_run(f)
        if data is None:
            continue

        run_date = data.get("run_date_utc", "")

        for q in data.get("queries", []):
            query_text = q.get("query", "")

            # Collect all citations: primary union + per-engine unions
            all_citations: list[dict] = list(q.get("citations_union", []))
            engines_for_url: dict[str, set[str]] = {}
            for eng_name, eng_data in (q.get("results_per_engine") or {}).items():
                for c in eng_data.get("citations_union", []):
                    u = c.get("url", "")
                    if u:
                        engines_for_url.setdefault(u, set()).add(eng_name)
                        all_citations.append(c)

            # Deduplicate within this query (same URL seen in primary + per-engine)
            seen_in_query: set[str] = set()
            for c in all_citations:
                url = c.get("url", "")
                if not url or url in seen_in_query:
                    continue
                if not _is_community(url, surface_filter, cats):
                    continue
                seen_in_query.add(url)

                if url not in url_data:
                    url_data[url] = {
                        "url": url,
                        "surface": categorize_url(url, cats),
                        "queries": set(),
                        "engines": set(),
                        "first_seen": run_date,
                        "last_seen": run_date,
                    }

                entry = url_data[url]
                entry["queries"].add(query_text)
                # Add engines: either from per-engine dict or infer from primary cited_by
                if url in engines_for_url:
                    entry["engines"].update(engines_for_url[url])
                else:
                    cited_by = q.get("cited_by", [])
                    entry["engines"].update(cited_by)

                if run_date and (not entry["first_seen"] or run_date < entry["first_seen"]):
                    entry["first_seen"] = run_date
                if run_date and run_date > entry["last_seen"]:
                    entry["last_seen"] = run_date

    # Convert sets → lists, filter, sort
    results: list[dict] = []
    for url, entry in url_data.items():
        query_count = len(entry["queries"])
        if query_count < min_query_count:
            continue
        engine_count = len(entry["engines"])
        results.append({
            "url": url,
            "surface": entry["surface"],
            "query_count": query_count,
            "engine_count": engine_count,
            "sample_queries": sorted(entry["queries"])[:3],
            "engines": sorted(entry["engines"]),
            "first_seen": entry["first_seen"],
            "last_seen": entry["last_seen"],
        })

    results.sort(
        key=lambda x: (-x["query_count"], -x["engine_count"], x["last_seen"]),
        reverse=False,
    )
    # Sort is ascending on negatives = descending on query_count/engine_count
    results = sorted(
        results,
        key=lambda x: (-x["query_count"], -x["engine_count"], x["last_seen"]),
    )

    return results[:top_n]
