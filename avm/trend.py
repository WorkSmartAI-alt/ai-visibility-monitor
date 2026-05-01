"""avm trend — historical citation trajectory analysis."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _load_run(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [trend] skipping {path.name}: {e}", file=sys.stderr)
        return None


def _run_date(data: dict) -> str:
    return data.get("run_date_utc", "")


def _queries_cited(data: dict, engine_filter: str | None, query_filter: str | None) -> tuple[int, int]:
    """Return (cited, total) for the filtered query set."""
    queries = data.get("queries", [])
    if query_filter:
        queries = [q for q in queries if query_filter.lower() in q.get("query", "").lower()]

    if not engine_filter:
        cited = sum(1 for q in queries if q.get("cited"))
        return cited, len(queries)

    # Per-engine filter: look in results_per_engine (v0.2.x) or fall back to primary
    cited = 0
    for q in queries:
        per_engine = q.get("results_per_engine", {})
        if per_engine:
            eng_data = per_engine.get(engine_filter)
            if eng_data and eng_data.get("cited"):
                cited += 1
        else:
            # v0.1.x — only Claude data, accept if engine_filter == "claude" or no filter
            if engine_filter == "claude" and q.get("cited"):
                cited += 1
    return cited, len(queries)


def _all_competitor_domains(data: dict, target_domain: str, query_filter: str | None) -> set[str]:
    domains: set[str] = set()
    for q in data.get("queries", []):
        if query_filter and query_filter.lower() not in q.get("query", "").lower():
            continue
        for c in q.get("citations_union", []):
            d = c.get("domain", "")
            if d and d != target_domain and target_domain not in d:
                domains.add(d)
        # Also pull from per-engine citations_union
        for eng_data in (q.get("results_per_engine") or {}).values():
            for c in eng_data.get("citations_union", []):
                d = c.get("domain", "")
                if d and d != target_domain and target_domain not in d:
                    domains.add(d)
    return domains


def compute_trend(
    data_dir: Path,
    query_filter: str | None = None,
    since: str | None = None,
    engine_filter: str | None = None,
) -> dict:
    """
    Read all citations-*.json files in data_dir chronologically, compute trajectory.

    Returns:
        {
          "target_domain": str,
          "runs": [{"date", "queries_cited", "queries_total", "delta_note"}],
          "new_competitors": [{"domain", "first_seen_run"}],
          "dropped_competitors": [{"domain", "last_seen_run"}],
          "per_query_trajectory": [],
        }
    """
    files = sorted(data_dir.glob("citations-20*.json"))
    # Exclude *-latest.json
    files = [f for f in files if "-latest" not in f.stem]

    if not files:
        return {
            "target_domain": "",
            "runs": [],
            "new_competitors": [],
            "dropped_competitors": [],
            "per_query_trajectory": [],
        }

    loaded: list[tuple[str, dict]] = []
    for f in files:
        data = _load_run(f)
        if data is None:
            continue
        date = _run_date(data)
        if since and date < since:
            continue
        loaded.append((date, data))

    if not loaded:
        return {
            "target_domain": "",
            "runs": [],
            "new_competitors": [],
            "dropped_competitors": [],
            "per_query_trajectory": [],
        }

    # Use target domain from most recent file
    target_domain = loaded[-1][1].get("target_domain", "")

    run_records: list[dict] = []
    all_comp_sets: list[set[str]] = []
    prev_cited = None

    for i, (date, data) in enumerate(loaded, 1):
        cited, total = _queries_cited(data, engine_filter, query_filter)
        delta_note = ""
        if prev_cited is not None:
            delta = cited - prev_cited
            if delta > 0:
                delta_note = f"↑ +{delta}"
            elif delta < 0:
                delta_note = f"↓ {delta}"
        prev_cited = cited
        run_records.append({
            "date": date,
            "run_number": i,
            "queries_cited": cited,
            "queries_total": total,
            "delta_note": delta_note,
        })
        all_comp_sets.append(_all_competitor_domains(data, target_domain, query_filter))

    # Compute new/dropped competitors
    new_competitors: list[dict] = []
    dropped_competitors: list[dict] = []

    if len(all_comp_sets) > 1:
        first_set = all_comp_sets[0]
        last_set = all_comp_sets[-1]

        for domain in last_set - first_set:
            # Find the first run it appeared
            for i, s in enumerate(all_comp_sets, 1):
                if domain in s:
                    new_competitors.append({"domain": domain, "first_seen_run": i})
                    break

        for domain in first_set - last_set:
            # Find the last run it appeared
            last_run = 1
            for i, s in enumerate(all_comp_sets, 1):
                if domain in s:
                    last_run = i
            dropped_competitors.append({"domain": domain, "last_seen_run": last_run})

    new_competitors.sort(key=lambda x: (x["first_seen_run"], x["domain"]))
    dropped_competitors.sort(key=lambda x: (x["last_seen_run"], x["domain"]))

    return {
        "target_domain": target_domain,
        "runs": run_records,
        "new_competitors": new_competitors,
        "dropped_competitors": dropped_competitors,
        "per_query_trajectory": [],
    }
