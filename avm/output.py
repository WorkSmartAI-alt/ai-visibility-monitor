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

        # Surface distribution with optional baseline annotations
        surf_dist = q.get("surface_distribution", {})
        if surf_dist:
            total_cites = sum(surf_dist.values())
            parts = []
            for cat, cnt in sorted(surf_dist.items(), key=lambda x: -x[1]):
                pct = int(cnt / total_cites * 100) if total_cites else 0
                parts.append(f"{pct}% {cat.replace('_', ' ')}")
            breakdown_text.append("     Surface mix: ", style="default")
            breakdown_text.append(" · ".join(parts) + "\n", style="dim")

            # Baseline annotations (shown when vertical is set and engines are known)
            vertical = result.get("vertical")
            active_engines = result.get("engines", [])
            if vertical and active_engines and total_cites > 0:
                try:
                    from avm.baselines import annotate_surface_distribution
                    from avm.surfaces import parent_distribution
                    parent_dist = parent_distribution(surf_dist)
                    for engine_name in active_engines[:1]:  # annotate against first/primary engine
                        annotations = annotate_surface_distribution(surf_dist, engine_name, vertical)
                        for parent_name, ann in sorted(annotations.items(), key=lambda x: -x[1]["count"]):
                            comp = ann.get("baseline")
                            if comp and comp["label"] != "at baseline":
                                est_marker = "~" if comp.get("is_estimated") else ""
                                pct = int(ann["share"] * 100)
                                bl_pct = int(comp["baseline"] * 100)
                                magnitude = comp["magnitude"]
                                label = comp["label"]
                                breakdown_text.append(
                                    f"       {parent_name}: {pct}%  "
                                    f"(baseline {est_marker}{bl_pct}%, {magnitude} {label})\n",
                                    style="dim",
                                )
                except Exception:
                    pass

            action = q.get("suggested_action", "")
            if action:
                breakdown_text.append("     Action: ", style="default")
                breakdown_text.append(action + "\n", style="italic dim")

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

    # RECOMMENDED TARGETS panel (only when --expand was used)
    recommended = result.get("recommended_targets", [])
    if recommended:
        console.print()
        targets_text = Text()
        targets_text.append("\n")
        for i, rec in enumerate(recommended, 1):
            score = int(rec.get("winnability_score", 0) * 100)
            targets_text.append(f"  {i}. ", style="default")
            targets_text.append(rec["query"] + "\n", style="bold")
            targets_text.append(f"     Winnability: {score}%  ·  ", style="dim")
            targets_text.append(rec.get("rationale", "") + "\n", style="italic dim")
            targets_text.append("\n")
        console.print(Panel(
            targets_text,
            title="[bold green]RECOMMENDED TARGETS[/bold green]",
            subtitle="[dim]queries to target in the next 30-60 days[/dim]",
            box=rich_box.ROUNDED,
            padding=(0, 0),
        ))


def pretty_print_trend(trend: dict) -> None:
    """Pretty-print avm trend output. Falls back to plain text if rich is unavailable."""
    if not _RICH_AVAILABLE:
        _plain_print_trend(trend)
        return

    console = Console()
    target = trend.get("target_domain", "")
    runs = trend.get("runs", [])
    new_competitors = trend.get("new_competitors", [])
    dropped_competitors = trend.get("dropped_competitors", [])

    console.print()
    title = f"CITATION TRAJECTORY · {target}" if target else "CITATION TRAJECTORY"
    trend_text = Text()
    trend_text.append("\n")

    for run in runs:
        date = run.get("date", "")
        cited = run.get("queries_cited", 0)
        total = run.get("queries_total", 0)
        delta_note = run.get("delta_note", "")
        trend_text.append(f"  {date}  ", style="dim")
        bar = "▏" + "█" * cited + " " * (total - cited)
        trend_text.append(bar + "  ", style="bold green" if cited > 0 else "dim")
        trend_text.append(f"{cited} of {total} cited", style="default")
        if delta_note:
            trend_text.append(f"  {delta_note}", style="dim green")
        trend_text.append("\n")

    if len(runs) >= 2:
        first_cited = runs[0].get("queries_cited", 0)
        last_cited = runs[-1].get("queries_cited", 0)
        delta = last_cited - first_cited
        total = runs[-1].get("queries_total", 1)
        if delta > 0:
            trajectory = f"improving (+{delta} in {len(runs)} runs)"
            traj_style = "bold green"
        elif delta < 0:
            trajectory = f"declining ({delta} in {len(runs)} runs)"
            traj_style = "bold red"
        else:
            trajectory = f"flat (no change over {len(runs)} runs)"
            traj_style = "bold yellow"
        trend_text.append(f"\n  Trajectory: ")
        trend_text.append(trajectory + "\n", style=traj_style)
    trend_text.append("\n")

    if new_competitors:
        trend_text.append("  New competitors appearing:\n", style="default")
        for comp in new_competitors:
            trend_text.append(f"    + {comp['domain']}", style="bold green")
            trend_text.append(f"  (since run {comp['first_seen_run']})\n", style="dim")
        trend_text.append("\n")

    if dropped_competitors:
        trend_text.append("  Competitors dropped:\n", style="default")
        for comp in dropped_competitors:
            trend_text.append(f"    - {comp['domain']}", style="bold red")
            trend_text.append(f"  (last seen run {comp['last_seen_run']})\n", style="dim")

    console.print(Panel(
        trend_text,
        title=f"[bold blue]{title}[/bold blue]",
        box=rich_box.ROUNDED,
        padding=(0, 0),
    ))
    console.print()


def _plain_print_trend(trend: dict) -> None:
    target = trend.get("target_domain", "")
    runs = trend.get("runs", [])
    print(f"\nCITATION TRAJECTORY — {target}")
    print("=" * 60)
    for run in runs:
        date = run.get("date", "")
        cited = run.get("queries_cited", 0)
        total = run.get("queries_total", 0)
        delta_note = run.get("delta_note", "")
        print(f"  {date}  {cited}/{total} cited  {delta_note}")
    new_competitors = trend.get("new_competitors", [])
    if new_competitors:
        print("\nNew competitors:")
        for c in new_competitors:
            print(f"  + {c['domain']}  (since run {c['first_seen_run']})")
    dropped_competitors = trend.get("dropped_competitors", [])
    if dropped_competitors:
        print("\nDropped competitors:")
        for c in dropped_competitors:
            print(f"  - {c['domain']}  (last seen run {c['last_seen_run']})")


def pretty_print_threads(threads: list[dict]) -> None:
    """Pretty-print avm threads output."""
    if not _RICH_AVAILABLE:
        _plain_print_threads(threads)
        return

    console = Console()
    console.print()

    if not threads:
        console.print(Panel(
            "\n  No community threads found.\n"
            "  Run avm with more historical data or lower --min-queries.\n",
            title="[bold blue]HIGH-LEVERAGE COMMUNITY THREADS[/bold blue]",
            box=rich_box.ROUNDED,
            padding=(0, 0),
        ))
        return

    text = Text()
    text.append("\n")
    for i, t in enumerate(threads, 1):
        url = t["url"]
        surface = t["surface"]
        query_count = t["query_count"]
        engine_count = t["engine_count"]
        engines = t.get("engines", [])
        sample_queries = t.get("sample_queries", [])
        last_seen = t.get("last_seen", "")

        text.append(f"  {i}. ", style="default")
        text.append(url + "\n", style="bold cyan")
        text.append(f"     Surface: ", style="default")
        text.append(f"{surface}", style="dim")
        if engines:
            from avm.engines import ENGINE_REGISTRY
            labels = [ENGINE_REGISTRY.get(e, {}).get("label", e) for e in engines]
            text.append(f"  ·  Cited by: {', '.join(labels)}", style="dim")
        text.append(f"  ·  {query_count} quer{'y' if query_count == 1 else 'ies'}\n", style="dim")
        if sample_queries:
            for sq in sample_queries[:2]:
                text.append(f"     Across: {sq}\n", style="italic dim")
        if last_seen:
            text.append(f"     Last seen: {last_seen}\n", style="dim")
        text.append("\n")

    text.append(
        "  Action: comment on these threads from your own account.\n"
        "  Do NOT use a posting service. Comments must come from\n"
        "  a real account that builds karma over time.\n",
        style="bold yellow",
    )

    console.print(Panel(
        text,
        title="[bold blue]HIGH-LEVERAGE COMMUNITY THREADS[/bold blue]",
        box=rich_box.ROUNDED,
        padding=(0, 0),
    ))
    console.print()


def _plain_print_threads(threads: list[dict]) -> None:
    print("\nHIGH-LEVERAGE COMMUNITY THREADS")
    print("=" * 60)
    if not threads:
        print("  No community threads found.")
        return
    for i, t in enumerate(threads, 1):
        print(f"  {i}. {t['url']}")
        print(f"     Surface: {t['surface']}  ·  {t['query_count']} queries  ·  engines: {', '.join(t.get('engines', []))}")
    print("\n  Action: comment on these threads from your own account.")
    print("  Do NOT use a posting service.")


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
