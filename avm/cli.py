from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _load_dotenv() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()

    parser = argparse.ArgumentParser(
        prog="avm",
        description="AI Visibility Monitor — track how AI engines cite your domain",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  avm                          run citation check (wizard on first run)\n"
            "  avm setup                    re-run the setup wizard\n"
            "  avm --engines claude         Claude only (v0.1.x behavior)\n"
            "  avm --model claude-sonnet-4-6 run with Sonnet instead of Haiku\n"
            "  avm --json                   raw JSON to stdout\n"
        ),
    )
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    parser.add_argument("--no-wizard", action="store_true", help="Skip first-run wizard (CI/scripted)")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip dependency preflight check")
    parser.add_argument("--model", default=None, help="Claude model to use (overrides Haiku default)")
    parser.add_argument("--runs", type=int, default=None, help="Runs per query (default: 2)")
    parser.add_argument("--json", dest="output_json", action="store_true", help="Raw JSON output to stdout")
    parser.add_argument("--quiet", action="store_true", help="Suppress all output except file path")
    parser.add_argument("--dry-run", action="store_true", help="Parse config only, no API call")
    parser.add_argument("--domain", default=None, help="Override primary domain from sites.json")
    parser.add_argument("--queries", default="queries.md", help="Path to queries file (default: queries.md)")
    parser.add_argument(
        "--engines",
        default=None,
        help="Engines to query (comma-separated: claude,chatgpt,perplexity). Default: all with keys",
    )
    parser.add_argument("--max-searches", type=int, default=5, help="Max web_search calls per run (Claude only)")
    parser.add_argument("--expand", action="store_true", help="Generate 15 adjacent queries and rank by winnability")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("setup", help="Run the setup wizard")
    subparsers.add_parser("citations", help="Run citation check (default when no subcommand)")
    subparsers.add_parser("gsc", help="Pull Google Search Console data")
    subparsers.add_parser("ga4", help="Pull GA4 data")
    subparsers.add_parser("prereqs", help="Audit robots.txt, llms.txt, sitemap")
    trend_parser = subparsers.add_parser("trend", help="Citation trajectory over time")
    trend_parser.add_argument("--query", default=None, help="Filter to queries matching this substring")
    trend_parser.add_argument("--since", default=None, help="Only include runs on or after this date (YYYY-MM-DD)")
    trend_parser.add_argument("--engine", default=None, help="Filter to a specific engine (claude, chatgpt, perplexity)")
    trend_parser.add_argument("--json", dest="output_json", action="store_true", help="Raw JSON output to stdout")

    args = parser.parse_args(argv)

    if args.version:
        from avm import __version__
        print(f"avm {__version__}")
        return 0

    if not args.skip_preflight:
        from avm.preflight import check_dependencies
        check_dependencies()

    if args.command is None:
        args.command = "citations"

    if args.command == "setup":
        from avm.wizard import run_wizard
        run_wizard(force=True)
        return 0

    if args.command == "citations":
        return _run_citations(args)

    if args.command == "gsc":
        from avm.gsc import main_cli
        return main_cli()

    if args.command == "ga4":
        from avm.ga4 import main_cli
        return main_cli()

    if args.command == "prereqs":
        from avm.prereqs import main_cli
        return main_cli()

    if args.command == "trend":
        return _run_trend(args)

    return 0


def _run_citations(args: argparse.Namespace) -> int:
    import json as json_mod
    from avm.citation import DEFAULT_MODEL, DEFAULT_RUNS, run_citation_check
    from avm.config import load_queries, load_sites
    from avm.output import write_json, pretty_print

    # Trigger wizard if config is incomplete
    if not args.no_wizard:
        from avm.wizard import should_run_wizard, run_wizard
        if should_run_wizard():
            proceed = run_wizard()
            if not proceed:
                return 0

    queries_path = Path(args.queries)
    if not queries_path.exists():
        print(f"ERROR: {queries_path} not found. Run 'avm setup' to configure.", file=sys.stderr)
        return 1

    queries = load_queries(queries_path)
    if not queries:
        print(f"ERROR: no queries found in {queries_path}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"[dry-run] loaded {len(queries)} queries from {queries_path.name}")
        for i, q in enumerate(queries, 1):
            print(f"  {i}. {q}")
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

    model = args.model or DEFAULT_MODEL
    runs = args.runs or DEFAULT_RUNS

    result = run_citation_check(
        queries=queries,
        target_domain=target_domain,
        competitors=competitors,
        model=model,
        runs_per_query=runs,
        engines=args.engines,
        max_searches=args.max_searches,
    )

    # --expand: generate adjacent queries, run citation check on them, rank by winnability
    if getattr(args, "expand", False):
        from avm.expansion import generate_adjacent_queries, score_expanded_queries
        from avm.citation import DEFAULT_MODEL as _DM
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        print("\n[expand] generating adjacent queries...", file=sys.stderr)
        try:
            adjacent = generate_adjacent_queries(
                base_queries=queries,
                target_count=15,
                model=model,
                api_key=api_key,
            )
        except RuntimeError as e:
            print(f"  [expand] skipped — {e}", file=sys.stderr)
            adjacent = []

        if adjacent:
            print(f"[expand] running citation check on {len(adjacent)} expanded queries...", file=sys.stderr)
            expanded_result = run_citation_check(
                queries=adjacent,
                target_domain=target_domain,
                competitors=competitors,
                model=model,
                runs_per_query=runs,
                engines=args.engines,
                max_searches=args.max_searches,
            )
            expanded_queries = expanded_result.get("queries", [])
            recommended = score_expanded_queries(expanded_queries, target_domain)[:5]
            result["expanded_queries"] = expanded_queries
            result["recommended_targets"] = recommended

    output_dir = Path("data")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"citations-{result['run_date_utc']}.json"
    write_json(result, output_path)

    if args.output_json:
        print(json_mod.dumps(result, indent=2))
        print(f"\n  JSON output written to: {output_path}", file=sys.stderr)
    else:
        if not args.quiet:
            pretty_print(result)
        print(f"\n  JSON output written to: {output_path}")
    return 0


def _run_trend(args: argparse.Namespace) -> int:
    import json as json_mod
    from avm.trend import compute_trend
    from avm.output import pretty_print_trend

    result = compute_trend(
        data_dir=Path("data"),
        query_filter=getattr(args, "query", None),
        since=getattr(args, "since", None),
        engine_filter=getattr(args, "engine", None),
    )

    if not result.get("runs"):
        print("No citation data found in data/. Run 'avm' first to generate data.", file=sys.stderr)
        return 1

    output_json = getattr(args, "output_json", False)
    if output_json:
        print(json_mod.dumps(result, indent=2))
    else:
        pretty_print_trend(result)
    return 0
