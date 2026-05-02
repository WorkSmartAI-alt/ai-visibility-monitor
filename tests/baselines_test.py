"""Tests for avm/baselines.py."""
import pytest
from avm.baselines import load_baselines, get_baseline, compare_to_baseline, annotate_surface_distribution


# ── load_baselines ─────────────────────────────────────────────────────────────
def test_load_returns_dict():
    data = load_baselines()
    assert isinstance(data, dict)
    assert "engines" in data
    assert "version" in data
    assert "source" in data


def test_known_engines_present():
    data = load_baselines()
    engines = data["engines"]
    assert "perplexity" in engines
    assert "chatgpt" in engines
    assert "claude" in engines


def test_perplexity_default_community():
    val = get_baseline("perplexity", "default", "community")
    assert val is not None
    assert 0.0 <= val <= 1.0
    assert val == pytest.approx(0.24, abs=0.01)  # Tinuiti Jan 2026


def test_chatgpt_default_community():
    val = get_baseline("chatgpt", "default", "community")
    assert val is not None
    assert val == pytest.approx(0.05, abs=0.01)


# ── get_baseline fallback ──────────────────────────────────────────────────────
def test_fallback_to_default_vertical():
    # "saas" is not a defined vertical → should fall back to default
    val = get_baseline("perplexity", "saas", "community")
    default_val = get_baseline("perplexity", "default", "community")
    assert val == default_val


def test_unknown_engine_returns_none():
    assert get_baseline("grok", "default", "community") is None


def test_unknown_surface_parent_returns_none():
    assert get_baseline("perplexity", "default", "nonexistent_surface") is None


# ── compare_to_baseline ────────────────────────────────────────────────────────
def test_at_baseline():
    # Perplexity default community = 0.24; actual ~0.24 → at baseline
    result = compare_to_baseline(0.24, "perplexity", "default", "community")
    assert result is not None
    assert result["label"] == "at baseline"
    assert result["magnitude"] == ""


def test_significantly_above():
    # 0.24 baseline, actual 0.50 → significantly above
    result = compare_to_baseline(0.50, "perplexity", "default", "community")
    assert result["label"] == "above average"
    assert result["magnitude"] == "significantly"


def test_slightly_above():
    # 0.24 baseline, actual 0.30 → slightly above
    result = compare_to_baseline(0.30, "perplexity", "default", "community")
    assert result["label"] == "above average"
    assert result["magnitude"] == "slightly"


def test_below_average():
    # 0.24 baseline, actual 0.05 → below average
    result = compare_to_baseline(0.05, "perplexity", "default", "community")
    assert result["label"] == "below average"


def test_unknown_engine_returns_none():
    result = compare_to_baseline(0.5, "grok", "default", "community")
    assert result is None


# ── annotate_surface_distribution ─────────────────────────────────────────────
def test_annotate_includes_community():
    leaf_dist = {"reddit": 5, "quora": 2, "press": 3}
    annotation = annotate_surface_distribution(leaf_dist, "perplexity", "default")
    assert "community" in annotation
    assert annotation["community"]["count"] == 7
    assert annotation["community"]["share"] == pytest.approx(0.7, abs=0.01)
    assert annotation["community"]["baseline"] is not None


def test_annotate_empty_dist():
    result = annotate_surface_distribution({}, "perplexity", "default")
    assert result == {}


def test_vertical_construction_data_present():
    val = get_baseline("perplexity", "construction", "community")
    assert val is not None
    assert val <= get_baseline("perplexity", "default", "community")  # B2B lower than default


def test_delta_sign():
    result = compare_to_baseline(0.10, "perplexity", "default", "community")
    # 0.10 < 0.24 → delta should be negative
    assert result["delta"] < 0
