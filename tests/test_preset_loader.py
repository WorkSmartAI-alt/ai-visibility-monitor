"""Tests for avm.preset_loader and the bundled work-smart-mid-market preset."""
from __future__ import annotations

import pytest
from avm.preset_loader import load_preset, list_presets, query_texts, Preset, Query


# ---------------------------------------------------------------------------
# Preset loading
# ---------------------------------------------------------------------------

def test_load_work_smart_mid_market_returns_preset():
    preset = load_preset("work-smart-mid-market")
    assert isinstance(preset, Preset)
    assert preset.slug == "work-smart-mid-market"


def test_work_smart_mid_market_has_21_queries():
    preset = load_preset("work-smart-mid-market")
    assert len(preset.queries) == 21, (
        f"Expected 21 queries, got {len(preset.queries)}. "
        f"IDs: {[q.id for q in preset.queries]}"
    )


def test_work_smart_mid_market_tier_summary():
    preset = load_preset("work-smart-mid-market")
    ts = preset.tier_summary
    assert ts.get("alpha") == 4
    assert ts.get("beta") == 8
    assert ts.get("gamma") == 8
    assert ts.get("s_tier") == 1
    assert sum(ts.values()) == 21


def test_work_smart_mid_market_all_queries_have_text():
    preset = load_preset("work-smart-mid-market")
    for q in preset.queries:
        assert q.text.strip(), f"Query {q.id} has empty text"


def test_work_smart_mid_market_all_queries_have_tier():
    preset = load_preset("work-smart-mid-market")
    valid_tiers = {"alpha", "beta", "gamma", "s_tier"}
    for q in preset.queries:
        assert q.tier in valid_tiers, f"Query {q.id} has unexpected tier: {q.tier}"


def test_work_smart_mid_market_all_queries_have_target_page():
    preset = load_preset("work-smart-mid-market")
    for q in preset.queries:
        assert q.target_page.startswith("/"), (
            f"Query {q.id} target_page should start with /: {q.target_page!r}"
        )


def test_work_smart_mid_market_alpha_queries():
    preset = load_preset("work-smart-mid-market")
    alpha = [q for q in preset.queries if q.tier == "alpha"]
    assert len(alpha) == 4
    texts = [q.text for q in alpha]
    assert any("fractional" in t.lower() or "cost" in t.lower() for t in texts)


def test_work_smart_mid_market_s_tier():
    preset = load_preset("work-smart-mid-market")
    s = [q for q in preset.queries if q.tier == "s_tier"]
    assert len(s) == 1
    assert "solopreneur" in s[0].text.lower() or "scale" in s[0].text.lower()


def test_work_smart_mid_market_query_ids_unique():
    preset = load_preset("work-smart-mid-market")
    ids = [q.id for q in preset.queries]
    assert len(ids) == len(set(ids)), f"Duplicate query IDs: {ids}"


def test_work_smart_mid_market_version():
    preset = load_preset("work-smart-mid-market")
    assert preset.version == "2.0"


def test_work_smart_mid_market_maintainer():
    preset = load_preset("work-smart-mid-market")
    assert "work-smart" in preset.maintainer.lower()


# ---------------------------------------------------------------------------
# query_texts helper
# ---------------------------------------------------------------------------

def test_query_texts_returns_list_of_strings():
    texts = query_texts("work-smart-mid-market")
    assert isinstance(texts, list)
    assert len(texts) == 21
    assert all(isinstance(t, str) for t in texts)


# ---------------------------------------------------------------------------
# list_presets
# ---------------------------------------------------------------------------

def test_list_presets_includes_work_smart():
    presets = list_presets()
    names = [p.name for p in presets]
    assert "work-smart-mid-market" in names


def test_list_presets_metadata_complete():
    presets = list_presets()
    for p in presets:
        assert p.slug
        assert p.query_count > 0
        assert p.version


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_load_nonexistent_preset_raises():
    with pytest.raises(FileNotFoundError, match="not found"):
        load_preset("does-not-exist")
