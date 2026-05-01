from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic SDK not installed. Run: pip install anthropic", file=sys.stderr)
    sys.exit(2)

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_RUNS = 2
DEFAULT_MAX_SEARCHES = 5

PROMPT_TEMPLATE = (
    "I'm researching this as a buyer. Give me a concise answer and cite the "
    "sources you used.\n\nQuery: {q}"
)


def domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _run_single_query(client: anthropic.Anthropic, model: str, query: str, max_searches: int) -> dict:
    """Call Claude with web_search enabled. Returns {citations, answer_text, ...}."""
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}]
    prompt = PROMPT_TEMPLATE.format(q=query)

    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        tools=tools,
        messages=[{"role": "user", "content": prompt}],
    )

    citations: list[dict] = []
    seen_urls: set[str] = set()
    answer_parts: list[str] = []

    for block in resp.content:
        btype = getattr(block, "type", None)
        if btype == "text":
            text = getattr(block, "text", "") or ""
            answer_parts.append(text)
            block_citations = getattr(block, "citations", None) or []
            for c in block_citations:
                ctype = getattr(c, "type", None)
                if ctype in ("web_search_result_location", "url_citation"):
                    url = getattr(c, "url", None) or ""
                    title = getattr(c, "title", None) or ""
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        citations.append({"url": url, "title": title, "domain": domain_of(url)})
        elif btype == "web_search_tool_result":
            content = getattr(block, "content", None) or []
            for item in content:
                url = getattr(item, "url", None) or ""
                title = getattr(item, "title", None) or ""
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    citations.append({
                        "url": url,
                        "title": title,
                        "domain": domain_of(url),
                        "from": "search_result",
                    })

    return {
        "query": query,
        "citations": citations,
        "answer_text": "".join(answer_parts).strip(),
        "stop_reason": getattr(resp, "stop_reason", None),
        "usage": {
            "input_tokens": getattr(getattr(resp, "usage", None), "input_tokens", None),
            "output_tokens": getattr(getattr(resp, "usage", None), "output_tokens", None),
        },
    }


def _position_of_domain(citations: list[dict], target_domain: str) -> int | None:
    for i, c in enumerate(citations, start=1):
        if target_domain in c["domain"]:
            return i
    return None


def _aggregate(query: str, runs: list[dict], target_domain: str) -> dict:
    """Union citations across runs, capture position stats for target domain."""
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


def run_citation_check(
    queries: list[str],
    target_domain: str,
    competitors: list[str] | None = None,
    model: str = DEFAULT_MODEL,
    runs_per_query: int = DEFAULT_RUNS,
    api_key: str | None = None,
) -> dict:
    """
    Run a citation check for the given queries against the target domain.

    Returns the citation result dict (same shape as v0.1.0 JSON output):
    {
        "run_date_utc": "...",
        "generator": "citation_check.py",
        "version": "1.0",
        "target_domain": "...",
        "model": "...",
        "runs_per_query": int,
        "summary": {...},
        "queries": [...],
    }
    """
    effective_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not effective_key:
        print("ERROR: ANTHROPIC_API_KEY not set in environment.", file=sys.stderr)
        print("Set it with: export ANTHROPIC_API_KEY='sk-ant-...'", file=sys.stderr)
        sys.exit(2)

    client = anthropic.Anthropic(api_key=effective_key)
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(f"[citation_check] target domain: {target_domain}")
    print(f"[citation_check] model: {model} | runs per query: {runs_per_query} | max searches: {DEFAULT_MAX_SEARCHES}\n")

    aggregated: list[dict] = []
    for i, query in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {query}")
        runs = []
        for r in range(runs_per_query):
            t0 = time.perf_counter()
            try:
                single = _run_single_query(client, model, query, DEFAULT_MAX_SEARCHES)
            except anthropic.APIError as e:
                print(f"    run {r+1}/{runs_per_query} FAILED: {e}", file=sys.stderr)
                continue
            runs.append(single)
            pos = _position_of_domain(single["citations"], target_domain)
            elapsed = int((time.perf_counter() - t0) * 1000)
            status = f"cited at #{pos}" if pos else f"not cited ({len(single['citations'])} URLs seen)"
            print(f"    run {r+1}/{runs_per_query}: {status} ({elapsed}ms)")
        agg = _aggregate(query, runs, target_domain)
        aggregated.append(agg)

    return {
        "run_date_utc": run_date,
        "generator": "citation_check.py",
        "version": "1.0",
        "target_domain": target_domain,
        "model": model,
        "runs_per_query": runs_per_query,
        "summary": {
            "queries_total": len(queries),
            "queries_cited": sum(1 for a in aggregated if a["cited"]),
            "queries_uncited": sum(1 for a in aggregated if not a["cited"]),
        },
        "queries": aggregated,
    }


def main_cli() -> int:
    from avm.config import load_queries, load_sites
    from avm.output import write_json, pretty_print

    parser = argparse.ArgumentParser(description="AI Visibility Monitor citation check")
    parser.add_argument("--domain", default=None, help="Target domain (overrides sites.json)")
    parser.add_argument("--queries", default="queries.md", help="Path to queries file")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS, help="Runs per query")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Claude model to use")
    parser.add_argument("--max-searches", type=int, default=DEFAULT_MAX_SEARCHES, help="Max web_search uses per query")
    parser.add_argument("--dry-run", action="store_true", help="Parse queries only, no API call")
    parser.add_argument("--json", dest="output_json", action="store_true", help="Raw JSON output to stdout")
    parser.add_argument("--quiet", action="store_true", help="Suppress all output except file write confirmation")
    parser.add_argument("--interactive", action="store_true", help="Set up queries.md interactively")
    parser.add_argument("--no-run", action="store_true", help="With --interactive, set up only")
    args = parser.parse_args()

    if args.interactive:
        from avm.interactive import run_interactive_setup
        run_interactive_setup()
        if args.no_run:
            return 0

    queries_path = Path(args.queries)
    if not queries_path.exists():
        print(f"ERROR: {queries_path} not found. Run --interactive to set up.", file=sys.stderr)
        return 1

    queries = load_queries(queries_path)
    if not queries:
        print(f"ERROR: no queries found in {queries_path}", file=sys.stderr)
        return 1

    print(f"[citation_check] loaded {len(queries)} queries from {queries_path.name}")
    for i, q in enumerate(queries, 1):
        print(f"  {i}. {q}")

    if args.dry_run:
        print("\n[dry-run] exiting without calling API.")
        return 0

    sites_path = Path("sites.json")
    if sites_path.exists():
        sites = load_sites(sites_path)
        target_domain = args.domain or sites["primary_domain"]
        competitors = sites.get("competitors", [])
    else:
        target_domain = args.domain or "example.com"
        competitors = []

    result = run_citation_check(
        queries=queries,
        target_domain=target_domain,
        competitors=competitors,
        model=args.model,
        runs_per_query=args.runs,
    )

    output_dir = Path("data")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"citations-{result['run_date_utc']}.json"
    write_json(result, output_path)

    if args.output_json:
        print(json.dumps(result, indent=2))
    elif not args.quiet:
        pretty_print(result)

    print(f"\n  JSON output written to: {output_path}")
    return 0
