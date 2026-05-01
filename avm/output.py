from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich import box as rich_box
    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False


def write_json(data: dict, path: Path) -> None:
    """Write data as pretty JSON to path and a sibling -latest.json file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, default=str)
    path.write_text(text, encoding="utf-8")
    # Derive the -latest sibling: "citations-2026-04-30" -> "citations-latest"
    stem = path.stem
    if len(stem) > 11 and stem[-11] == "-":
        prefix = stem[:-11]
        latest = path.parent / f"{prefix}-latest{path.suffix}"
        latest.write_text(text, encoding="utf-8")


def _top_competitor(result: dict) -> tuple[str, int] | None:
    """Find the competitor domain cited in the most queries, across all engines."""
    counts: Counter = Counter()
    target = result.get("target_domain", "")
    for q in result.get("queries", []):
        seen_in_query: set[str] = set()
        # Collect all citation sources: primary union + per-engine unions
        all_citations: list[dict] = list(q.get("citations_union", []))
        for eng_data in (q.get("results_per_engine") or {}).values():
            all_citations.extend(eng_data.get("citations_union", []))
        for c in all_citations:
            d = c.get("domain", "")
            if d and d != target and target not in d and d not in seen_in_query:
                seen_in_query.add(d)
                counts[d] += 1
    return counts.most_common(1)[0] if counts else None


def _top_competitors_for_query(q: dict, target_domain: str, n: int = 3) -> list[str]:
    """Return the first n competitor domains cited in a query."""
    domains: list[str] = []
    seen: set[str] = set()
    for c in q.get("citations_union", []):
        d = c.get("domain", "")
        if d and d != target_domain and target_domain not in d and d not in seen:
            seen.add(d)
            domains.append(d)
        if len(domains) >= n:
            break
    return domains


def pretty_print(result: dict) -> None:
    """Pretty-print a citation check result. Falls back to plain text if rich is unavailable."""
    if not _RICH_AVAILABLE:
        _plain_print(result)
        return

    console = Console()
    target = result.get("target_domain", "")
    run_date = result.get("run_date_utc", "")
    model = result.get("model", "")
    runs_per_query = result.get("runs_per_query", 0)
    summary = result.get("summary", {})
    queries_total = summary.get("queries_total", 0)
    queries_cited = summary.get("queries_cited", 0)
    queries = result.get("queries", [])

    # Header panel
    header = Text()
    header.append("AI VISIBILITY MONITOR\n", style="bold")
    header.append(target, style="bold yellow")
    header.append(f" · {run_date}", style="default")
    console.print()
    console.print(Panel(header, box=rich_box.ROUNDED, padding=(0, 2)))

    # Run config
    console.print()
    console.print(f"  Model:          {model}")
    console.print(f"  Runs per query: {runs_per_query}")
    console.print(f"  Queries:        {queries_total}")
    console.print()

    # Summary panel
    rate = queries_cited / queries_total if queries_total else 0.0
    if rate <= 0.25:
        cite_style = "bold red"
    elif rate <= 0.50:
        cite_style = "bold yellow"
    else:
        cite_style = "bold green"

    top_comp = _top_competitor(result)
    summary_text = Text()
    summary_text.append("\n")
    summary_text.append(
        f"  ⬤ {queries_cited} of {queries_total} queries cited your domain\n",
        style=cite_style,
    )
    if top_comp:
        summary_text.append("  ⬤ Most-cited competitor: ", style="default")
        summary_text.append(top_comp[0], style="dim cyan")
        summary_text.append(f" ({top_comp[1]})\n", style="default")
    summary_text.append(" ")
    console.print(Panel(
        summary_text,
        title="[bold blue]SUMMARY[/bold blue]",
        box=rich_box.ROUNDED,
        padding=(0, 0),
    ))
    console.print()

    # Per-query breakdown panel
    breakdown_text = Text()
    breakdown_text.append("\n")
    for i, q in enumerate(queries, 1):
        cited = q.get("cited", False)
        cite_rate = int(q.get("citation_rate", 0.0) * 100)
        breakdown_text.append(f"  {i}. {q['query']}\n", style="bold")
        breakdown_text.append("     Cited: ", style="default")
        if cited:
            breakdown_text.append("✓", style="bold green")
            cited_by = q.get("cited_by", [])
            if cited_by:
                from avm.engines import ENGINE_REGISTRY
                labels = [ENGINE_REGISTRY.get(e, {}).get("label", e) for e in cited_by]
                breakdown_text.append(f" ({', '.join(labels)})", style="bold green")
        else:
            breakdown_text.append("✗", style="bold red")
        breakdown_text.append(f"  ·  Citation rate: {cite_rate}%\n", style="default")

        # Per-engine breakdown (multi-engine mode)
        per_engine = q.get("results_per_engine")
        if per_engine:
            engine_parts: list[str] = []
            from avm.engines import ENGINE_REGISTRY
            for eng_name, eng_data in per_engine.items():
                label = ENGINE_REGISTRY.get(eng_name, {}).get("label", eng_name)
                tick = "cited" if eng_data.get("cited") else "not cited"
                engine_parts.append(f"{label}: {tick}")
            breakdown_text.append("     Engines: ", style="default")
            breakdown_text.append(" / ".join(engine_parts) + "\n", style="dim")

        comps = _top_competitors_for_query(q, target)
        if comps:
            breakdown_text.append("     Top competitors:\n", style="default")
            for comp in comps:
                breakdown_text.append("       → ", style="default")
                breakdown_text.append(f"{comp}\n", style="dim cyan")
        breakdown_text.append("\n")
    console.print(Panel(
        breakdown_text,
        title="[bold blue]PER-QUERY BREAKDOWN[/bold blue]",
        box=rich_box.ROUNDED,
        padding=(0, 0),
    ))


def _plain_print(result: dict) -> None:
    """Plain text fallback when rich is not available."""
    print("\nNote: install 'rich' for the polished output (pip install rich)")
    target = result.get("target_domain", "")
    run_date = result.get("run_date_utc", "")
    summary = result.get("summary", {})
    queries_cited = summary.get("queries_cited", 0)
    queries_total = summary.get("queries_total", 0)
    engines = result.get("engines", [])
    print(f"\nAI VISIBILITY MONITOR - {target} - {run_date}")
    if engines:
        print(f"Engines: {', '.join(engines)}")
    print("=" * 60)
    print(f"Cited in {queries_cited} of {queries_total} queries.")
    for q in result.get("queries", []):
        cited_by = q.get("cited_by", [])
        if q.get("cited") and cited_by:
            tag = f"YES ({', '.join(cited_by)})"
        elif q.get("cited"):
            tag = f"YES #{q.get('position_mode', '?')}"
        else:
            tag = "NO"
        print(f"  [{tag}]  {q['query']}")
        per_engine = q.get("results_per_engine")
        if per_engine:
            parts = [f"{eng}: {'cited' if d.get('cited') else 'not cited'}" for eng, d in per_engine.items()]
            print(f"           {' / '.join(parts)}")
