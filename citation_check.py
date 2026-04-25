#!/usr/bin/env python3
"""
Citation Check · AI Visibility Monitor

For each query in queries.md, asks Claude a buyer-style question with the
web_search tool enabled, then records which URLs Claude cited and whether
your target domain is among them.

Why Claude with web_search:
  - It measures one of the engines your ICP increasingly uses.
  - The same approach can be extended to Perplexity Sonar or other providers
    by swapping the client and prompt template.

Requirements:
  pip install anthropic

Environment:
  ANTHROPIC_API_KEY must be set.

Usage:
  python3 citation_check.py                                # uses defaults
  python3 citation_check.py --domain example.com --runs 3
  python3 citation_check.py --dry-run                      # parses queries only

Setup:
  cp queries.md.example queries.md
  # edit queries.md with your 5 buyer queries

Output:
  ./data/citations-YYYY-MM-DD.json     # dated snapshot
  ./data/citations-latest.json         # stable filename for downstream dashboards

The JSON records, per query, every citation seen across N runs (union),
plus the mode position of the target domain. Multiple runs per query
smooth non-determinism in Claude's web_search behavior.

Part of the AI Visibility Monitor toolkit. Built by Ignacio Lopez (Work-Smart.ai).
MIT licensed. https://github.com/WorkSmartAI-alt/ai-visibility-monitor
"""
from __future__ import annotations

import argparse
import json
import os
import re
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


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "claude-sonnet-4-6"       # cost-optimized, supports web_search
DEFAULT_QUERIES_FILE = "queries.md"
DEFAULT_DOMAIN = "example.com"
DEFAULT_RUNS = 2                           # Claude is less deterministic than Sonar, take 2 samples
DEFAULT_MAX_SEARCHES = 5                  # cap web_search uses per query

# Answer framing prompt prefix. We are not writing content, we are simulating a
# buyer query so Claude goes to the web and cites real URLs.
PROMPT_TEMPLATE = (
    "I'm researching this as a buyer. Give me a concise answer and cite the "
    "sources you used.\n\nQuery: {q}"
)


# ---------------------------------------------------------------------------
# Query loading
# ---------------------------------------------------------------------------

def load_queries(path: Path) -> list[str]:
    """
    queries.md has an H1 title, an optional blockquote intro, the 5 queries
    as plain lines, then a "## Rules..." section we ignore.
    """
    queries: list[str] = []
    stop = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        # Any subsection heading (##, ###, ...) means we're past the query list
        if re.match(r"^#{2,}\s", line):
            stop = True
            continue
        if stop:
            continue
        # Skip the H1 title, blockquote commentary, and code fences
        if line.startswith("#") or line.startswith(">") or line.startswith("```"):
            continue
        # Strip optional list markers
        line = re.sub(r"^[-*+]\s+", "", line)
        line = re.sub(r"^\d+[.)]\s+", "", line)
        # Strip surrounding quotes if present
        if (line.startswith('"') and line.endswith('"')) or (line.startswith("'") and line.endswith("'")):
            line = line[1:-1]
        if line:
            queries.append(line)
    return queries[:10]  # hard cap, we only want 5ish


# ---------------------------------------------------------------------------
# Anthropic web_search call
# ---------------------------------------------------------------------------

def domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def run_query(client: anthropic.Anthropic, model: str, query: str, max_searches: int) -> dict:
    """
    Call Claude with web_search enabled. Returns {citations, answer_text, raw}.
    citations is a list of unique {url, title, domain, text_before} objects in
    the order Claude referenced them.
    """
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
            # Each text block may have a .citations list with url_citation entries
            block_citations = getattr(block, "citations", None) or []
            for c in block_citations:
                ctype = getattr(c, "type", None)
                if ctype in ("web_search_result_location", "url_citation"):
                    url = getattr(c, "url", None) or ""
                    title = getattr(c, "title", None) or ""
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        citations.append({
                            "url": url,
                            "title": title,
                            "domain": domain_of(url),
                        })
        elif btype == "web_search_tool_result":
            # The raw search results Claude saw. Use these as a fallback
            # source of URLs in case the text block citations were missed.
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


# ---------------------------------------------------------------------------
# Multi-run aggregation
# ---------------------------------------------------------------------------

def position_of_domain(citations: list[dict], target_domain: str) -> int | None:
    for i, c in enumerate(citations, start=1):
        if target_domain in c["domain"]:
            return i
    return None


def aggregate(query: str, runs: list[dict], target_domain: str) -> dict:
    """Union citations across runs, capture position stats for target domain."""
    union: list[dict] = []
    seen: set[str] = set()
    positions: list[int] = []

    for run in runs:
        pos = position_of_domain(run["citations"], target_domain)
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help="Target domain to look for in citations")
    parser.add_argument("--queries", default=DEFAULT_QUERIES_FILE, help="Path to queries.md")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS, help="How many times to query each prompt (non-determinism smoothing)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Claude model to use")
    parser.add_argument("--max-searches", type=int, default=DEFAULT_MAX_SEARCHES, help="Max web_search tool uses per query")
    parser.add_argument("--dry-run", action="store_true", help="Parse queries only, no API call")
    parser.add_argument("--output-dir", default=None, help="Override output directory (default: ./data/)")
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    queries_path = (here / args.queries).resolve() if not Path(args.queries).is_absolute() else Path(args.queries)
    output_dir = Path(args.output_dir) if args.output_dir else (here / "data")
    output_dir.mkdir(parents=True, exist_ok=True)

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

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\nERROR: ANTHROPIC_API_KEY not set in environment.", file=sys.stderr)
        print("Set it with: export ANTHROPIC_API_KEY='sk-ant-...'", file=sys.stderr)
        return 2

    client = anthropic.Anthropic()
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"\n[citation_check] target domain: {args.domain}")
    print(f"[citation_check] model: {args.model} | runs per query: {args.runs} | max searches: {args.max_searches}\n")

    aggregated: list[dict] = []
    for i, query in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {query}")
        runs = []
        for r in range(args.runs):
            t0 = time.perf_counter()
            try:
                result = run_query(client, args.model, query, args.max_searches)
            except anthropic.APIError as e:
                print(f"    run {r+1}/{args.runs} FAILED: {e}", file=sys.stderr)
                continue
            runs.append(result)
            pos = position_of_domain(result["citations"], args.domain)
            elapsed = int((time.perf_counter() - t0) * 1000)
            status = f"cited at #{pos}" if pos else f"not cited ({len(result['citations'])} URLs seen)"
            print(f"    run {r+1}/{args.runs}: {status} ({elapsed}ms)")
        agg = aggregate(query, runs, args.domain)
        aggregated.append(agg)

    bundle = {
        "run_date_utc": run_date,
        "generator": "citation_check.py",
        "version": "1.0",
        "target_domain": args.domain,
        "model": args.model,
        "runs_per_query": args.runs,
        "summary": {
            "queries_total": len(queries),
            "queries_cited": sum(1 for a in aggregated if a["cited"]),
            "queries_uncited": sum(1 for a in aggregated if not a["cited"]),
        },
        "queries": aggregated,
    }

    out_path = output_dir / f"citations-{run_date}.json"
    out_path.write_text(json.dumps(bundle, indent=2, default=str), encoding="utf-8")
    (output_dir / "citations-latest.json").write_text(json.dumps(bundle, indent=2, default=str), encoding="utf-8")

    # Print a tiny summary so the terminal output tells the story
    print()
    print("=" * 60)
    print(f"CITATION CHECK · {run_date} · {args.domain}")
    print("=" * 60)
    cited = bundle["summary"]["queries_cited"]
    total = bundle["summary"]["queries_total"]
    print(f"Cited in {cited} of {total} queries.")
    for a in aggregated:
        tag = f"YES #{a['position_mode']}" if a["cited"] else "NO"
        print(f"  [{tag:>6}]  {a['query']}")
    print()
    print(f"JSON: {out_path}")
    print(f"JSON: {output_dir / 'citations-latest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
