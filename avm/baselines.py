"""Vertical baseline surface-share data for annotating AVM output."""
from __future__ import annotations

import json
from pathlib import Path

_BASELINES_PATH = Path(__file__).parent / "data" / "baselines.json"
_cache: dict | None = None


def load_baselines() -> dict:
    """Load baselines.json (cached after first call)."""
    global _cache
    if _cache is None:
        _cache = json.loads(_BASELINES_PATH.read_text(encoding="utf-8"))
    return _cache


def get_baseline(engine: str, vertical: str, surface_parent: str) -> float | None:
    """
    Return the baseline surface share (0.0–1.0) for a given engine/vertical/surface_parent.
    Falls back to 'default' vertical if the specific vertical is unknown.
    Returns None if no data exists for the engine.
    """
    data = load_baselines()
    engines = data.get("engines", {})

    if engine not in engines:
        return None

    eng_data = engines[engine]
    # Try specific vertical first, fall back to default
    vertical_data = eng_data.get(vertical) or eng_data.get("default")
    if vertical_data is None:
        return None

    return vertical_data.get(surface_parent)


def compare_to_baseline(
    actual_share: float,
    engine: str,
    vertical: str,
    surface_parent: str,
) -> dict | None:
    """
    Compare actual_share against the baseline.

    Returns dict with:
        baseline: float
        delta: float  (actual - baseline)
        label: "above average" | "at baseline" | "below average"
        magnitude: "significantly" | "slightly" | ""
        is_estimated: bool

    Returns None if no baseline data exists for this combination.
    """
    baseline = get_baseline(engine, vertical, surface_parent)
    if baseline is None:
        return None

    delta = round(actual_share - baseline, 3)
    abs_delta = abs(delta)

    if abs_delta < 0.05:
        label = "at baseline"
        magnitude = ""
    elif delta > 0:
        label = "above average"
        magnitude = "significantly" if abs_delta > 0.15 else "slightly"
    else:
        label = "below average"
        magnitude = "significantly" if abs_delta > 0.15 else "slightly"

    # Check if this vertical data is estimated
    data = load_baselines()
    vertical_data = (
        data.get("engines", {}).get(engine, {}).get(vertical)
        or data.get("engines", {}).get(engine, {}).get("default", {})
    )
    is_estimated = bool(vertical_data.get("_estimated")) or bool(
        data.get("engines", {}).get(engine, {}).get("_note")
    )

    return {
        "baseline": baseline,
        "delta": delta,
        "label": label,
        "magnitude": magnitude,
        "is_estimated": is_estimated,
    }


def annotate_surface_distribution(
    leaf_dist: dict[str, int],
    engine: str,
    vertical: str,
) -> dict[str, dict]:
    """
    For each parent surface in leaf_dist, compute the baseline comparison.
    Returns {surface_parent: {share, baseline_info}} for surfaces with baseline data.
    """
    from avm.surfaces import parent_distribution

    parent_dist = parent_distribution(leaf_dist)
    total = sum(parent_dist.values())
    if total == 0:
        return {}

    result: dict[str, dict] = {}
    for parent, count in parent_dist.items():
        share = round(count / total, 3)
        comparison = compare_to_baseline(share, engine, vertical, parent)
        result[parent] = {
            "count": count,
            "share": share,
            "baseline": comparison,
        }
    return result
