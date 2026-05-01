from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_RUNS = 2
DEFAULT_MAX_SEARCHES = 5


def domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


# ── kept for backward-compat with any code importing from avm.citation directly ──
def _run_single_query(client, model: str, query: str, max_searches: int) -> dict:
    """Direct Claude call. Imported by tests and the head-to-head comparison script."""
    from avm.engines.claude import _run_single
    result = _run_single(client, model, query, max_searches)
    return {
        "query": query,
        "citations": result["citations"],
        "answer_text": "",
        "stop_reason": result["stop_reason"],
        "usage": {},
    }


def _position_of_domain(citations: list[dict], target_domain: str) -> int | None:
    for i, c in enumerate(citations, start=1):
        if target_domain in c["domain"]:
            return i
    return None


def _aggregate(query: str, runs: list[dict], target_domain: str) -> dict:
    import statistics
    union: list[dict] = []
    seen: set[str] = set()
    positions: list[int] = []
    for run in runs:
        pos = _position_of_domain(run["citations"], target_domain)
        if pos is not None:
            positions.append(pos)
        for c in run["citations"]:
            if c["url"] not in seen:
                seen.add(c["url"])
                union.append(c)
    cited = len(positions) > 0
    return {
        "query": query,
        "runs": len(runs),
        "cited": cited,
        "citation_rate": round(len(positions) / len(runs), 2) if runs else 0,
        "position_mode": statistics.mode(positions) if positions else None,
        "position_min": min(positions) if positions else None,
        "position_max": max(positions) if positions else None,
        "citations_union": union,
        "raw_runs": runs,
    }


def _parse_engines(engines_arg: str | list[str] | None) -> list[str]:
    from avm.engines import ENGINE_ORDER
    if engines_arg is None:
        return list(ENGINE_ORDER)
    if isinstance(engines_arg, str):
        return [e.strip().lower() for e in engines_arg.split(",") if e.strip()]
    return [e.strip().lower() for e in engines_arg]


def _resolve_available(
    engine_list: list[str],
    claude_api_key: str | None,
) -> list[tuple[str, str, str]]:
    """
    Return list of (engine_name, api_key, model) for engines that have keys.
    Warns and skips engines without keys.
    """
    from avm.engines import ENGINE_REGISTRY
    available: list[tuple[str, str, str]] = []
    for eng in engine_list:
        if eng not in ENGINE_REGISTRY:
            print(f"  [warning] Unknown engine '{eng}', skipping.", file=sys.stderr)
            continue
        reg = ENGINE_REGISTRY[eng]
        key = claude_api_key if eng == "claude" else None
        key = key or os.environ.get(reg["api_key_env"], "")
        if not key:
            print(f"  [warning] No {reg['api_key_env']} set — skipping {reg['label']}.")
            continue
        available.append((eng, key, reg["default_model"]))
    return available


def _call_engine(eng_name: str, query: str, target_domain: str, key: str, model: str,
                 runs: int, max_searches: int) -> dict | None:
    import importlib
    from avm.engines import ENGINE_REGISTRY
    try:
        mod = importlib.import_module(ENGINE_REGISTRY[eng_name]["module"])
        return mod.run_query(
            query=query,
            target_domain=target_domain,
            model=model,
            api_key=key,
            runs=runs,
            max_searches=max_searches,
        )
    except RuntimeError as e:
        print(f"  [warning] {eng_name}: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [warning] {eng_name} failed: {e}", file=sys.stderr)
        return None


def run_citation_check(
    queries: list[str],
    target_domain: str,
    competitors: list[str] | None = None,
    model: str = DEFAULT_MODEL,
    runs_per_query: int = DEFAULT_RUNS,
    api_key: str | None = None,
    engines: str | list[str] | None = None,
    max_searches: int = DEFAULT_MAX_SEARCHES,
) -> dict:
    """
    Run a citation check across one or more AI engines.

    When engines='claude' or only Claude is available, the output shape is
    identical to v0.1.0 (backward compatible). When multiple engines run,
    each query additionally contains a 'results_per_engine' dict.
    """
    effective_claude_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    engine_list = _parse_engines(engines)
    available = _resolve_available(engine_list, effective_claude_key)

    if not available:
        print("ERROR: No engine API keys found. Set ANTHROPIC_API_KEY at minimum.", file=sys.stderr)
        sys.exit(1)

    # Use the caller-supplied model for Claude, registry default for others
    engine_models: dict[str, str] = {}
    from avm.engines import ENGINE_REGISTRY
    for eng, _key, default_model in available:
        engine_models[eng] = model if eng == "claude" else default_model

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    active_engine_names = [e for e, _, _ in available]
    multi = len(available) > 1

    print(f"[citation_check] target: {target_domain}", file=sys.stderr)
    print(f"[citation_check] engines: {', '.join(active_engine_names)}", file=sys.stderr)
    print(f"[citation_check] claude model: {engine_models.get('claude', model)} | runs: {runs_per_query}\n", file=sys.stderr)

    aggregated: list[dict] = []
    for i, query in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {query}", file=sys.stderr)
        results_per_engine: dict[str, dict] = {}

        for eng_name, eng_key, _ in available:
            eng_result = _call_engine(
                eng_name, query, target_domain, eng_key,
                engine_models[eng_name], runs_per_query, max_searches,
            )
            if eng_result is not None:
                results_per_engine[eng_name] = eng_result

        # Primary engine for backward-compat fields: Claude if available, else first
        primary_name = "claude" if "claude" in results_per_engine else (
            next(iter(results_per_engine), None)
        )
        if primary_name is None:
            print(f"  [warning] all engines failed for query {i+1}", file=sys.stderr)
            continue

        primary = results_per_engine[primary_name]

        # Cross-engine aggregation: cited if ANY engine cited the domain
        any_cited = any(r["cited"] for r in results_per_engine.values())
        best_rate = max((r["citation_rate"] for r in results_per_engine.values()), default=0.0)
        cited_by = [eng for eng, r in results_per_engine.items() if r["cited"]]

        # Surface distribution across all cited URLs (all engines combined)
        from avm.surfaces import surface_distribution, suggested_action
        all_urls: list[dict] = list(primary["citations_union"])
        if multi:
            for r in results_per_engine.values():
                for c in r.get("citations_union", []):
                    if not any(x["url"] == c["url"] for x in all_urls):
                        all_urls.append(c)
        surf_dist = surface_distribution(all_urls)
        surf_action = suggested_action(surf_dist)

        query_result: dict = {
            "query": query,
            "runs": primary["runs"],
            "cited": any_cited,
            "citation_rate": best_rate,
            "cited_by": cited_by,
            "position_mode": primary.get("position_mode"),
            "position_min": primary.get("position_min"),
            "position_max": primary.get("position_max"),
            "citations_union": primary["citations_union"],
            "surface_distribution": surf_dist,
            "suggested_action": surf_action,
            "raw_runs": primary["raw_runs"],
        }
        if multi:
            query_result["results_per_engine"] = {
                eng: {
                    "cited": r["cited"],
                    "citation_rate": r["citation_rate"],
                    "citations_union": r["citations_union"],
                }
                for eng, r in results_per_engine.items()
            }
        aggregated.append(query_result)

    total = len(aggregated)
    cited_count = sum(1 for a in aggregated if a["cited"])
    return {
        "run_date_utc": run_date,
        "generator": "citation_check.py",
        "version": "1.0",
        "target_domain": target_domain,
        "model": engine_models.get("claude", model),
        "engines": active_engine_names,
        "runs_per_query": runs_per_query,
        "summary": {
            "queries_total": total,
            "queries_cited": cited_count,
            "queries_uncited": total - cited_count,
        },
        "queries": aggregated,
    }


def main_cli() -> int:
    """Legacy entry point — delegates to avm.cli.main() for full feature support."""
    from avm.cli import main
    return main()
