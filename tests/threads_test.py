"""Tests for avm/threads.py — find_top_threads()."""
import json
import pytest
from pathlib import Path
from avm.threads import find_top_threads


def _write_run(tmp_path: Path, filename: str, queries: list[dict], date: str = "2026-05-01") -> Path:
    data = {
        "run_date_utc": date,
        "target_domain": "work-smart.ai",
        "engines": ["claude", "perplexity"],
        "runs_per_query": 2,
        "summary": {"queries_total": len(queries), "queries_cited": 0, "queries_uncited": len(queries)},
        "queries": queries,
    }
    p = tmp_path / filename
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _q(query: str, citations: list[dict], cited_by: list[str] | None = None) -> dict:
    return {
        "query": query,
        "cited": bool(cited_by),
        "cited_by": cited_by or [],
        "citation_rate": 0.0,
        "citations_union": citations,
    }


def _c(url: str) -> dict:
    from urllib.parse import urlparse
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return {"url": url, "title": "", "domain": host}


# ── scenario 1: basic ranking by query_count ──────────────────────────────────
def test_ranks_by_query_count(tmp_path):
    _write_run(tmp_path, "citations-2026-05-01.json", [
        _q("fractional head of ai", [
            _c("https://reddit.com/r/consulting/comments/abc"),
            _c("https://reddit.com/r/MachineLearning/comments/xyz"),
        ]),
        _q("ai for mid-market", [
            _c("https://reddit.com/r/consulting/comments/abc"),  # same thread, 2nd query
            _c("https://quora.com/What-is-fractional-ai"),
        ]),
        _q("ai consultant cost", [
            _c("https://quora.com/What-is-fractional-ai"),  # quora cited in 2 queries
        ]),
    ])
    threads = find_top_threads(tmp_path, min_query_count=1)
    assert len(threads) >= 2
    # reddit/consulting/abc is cited in 2 queries, quora in 2 queries — both should be top
    urls = [t["url"] for t in threads]
    assert "https://reddit.com/r/consulting/comments/abc" in urls
    assert "https://quora.com/What-is-fractional-ai" in urls
    # The first two should have query_count >= 2
    assert threads[0]["query_count"] >= 2
    assert threads[1]["query_count"] >= 2


# ── scenario 2: surface_filter restricts to reddit only ──────────────────────
def test_surface_filter_reddit_only(tmp_path):
    _write_run(tmp_path, "citations-2026-05-01.json", [
        _q("fractional ai", [
            _c("https://reddit.com/r/ai/comments/abc"),
            _c("https://quora.com/What-is-ai"),
            _c("https://stackoverflow.com/questions/123"),
        ]),
    ])
    threads = find_top_threads(tmp_path, surface_filter=["reddit"], min_query_count=1)
    assert all(t["surface"] == "reddit" for t in threads)
    assert len(threads) == 1
    assert threads[0]["url"] == "https://reddit.com/r/ai/comments/abc"


# ── scenario 3: min_queries threshold filters results ────────────────────────
def test_min_queries_threshold(tmp_path):
    _write_run(tmp_path, "citations-2026-05-01.json", [
        _q("query A", [_c("https://reddit.com/r/ai/comments/once")]),
        _q("query B", [
            _c("https://reddit.com/r/ai/comments/twice"),
            _c("https://reddit.com/r/ai/comments/twice"),  # same url, still 1 query
        ]),
        _q("query C", [_c("https://reddit.com/r/ai/comments/twice")]),
    ])
    # With min_queries=2, only "twice" qualifies
    threads = find_top_threads(tmp_path, min_query_count=2)
    assert len(threads) == 1
    assert "twice" in threads[0]["url"]


# ── scenario 4: empty data dir returns empty list ────────────────────────────
def test_empty_data_dir(tmp_path):
    threads = find_top_threads(tmp_path, min_query_count=1)
    assert threads == []


# ── scenario 5: malformed JSON files are skipped gracefully ──────────────────
def test_malformed_json_skipped(tmp_path):
    bad = tmp_path / "citations-2026-04-01.json"
    bad.write_text("{ not valid json ::::", encoding="utf-8")
    good = _write_run(tmp_path, "citations-2026-05-01.json", [
        _q("ai consulting", [_c("https://reddit.com/r/ai/comments/good")]),
    ])
    threads = find_top_threads(tmp_path, min_query_count=1)
    assert len(threads) == 1
    assert "good" in threads[0]["url"]


# ── scenario 6: top_n caps results ───────────────────────────────────────────
def test_top_n_cap(tmp_path):
    citations = [
        _c(f"https://reddit.com/r/ai/comments/{i}") for i in range(10)
    ]
    _write_run(tmp_path, "citations-2026-05-01.json", [
        _q("some query", citations),
    ])
    threads = find_top_threads(tmp_path, top_n=3, min_query_count=1)
    assert len(threads) <= 3


# ── scenario 7: per-engine citations are attributed correctly ─────────────────
def test_per_engine_citations(tmp_path):
    data = {
        "run_date_utc": "2026-05-01",
        "target_domain": "work-smart.ai",
        "engines": ["claude", "perplexity"],
        "runs_per_query": 2,
        "summary": {"queries_total": 1, "queries_cited": 0, "queries_uncited": 1},
        "queries": [{
            "query": "ai consulting",
            "cited": False,
            "cited_by": [],
            "citation_rate": 0.0,
            "citations_union": [],
            "results_per_engine": {
                "perplexity": {
                    "cited": False,
                    "citation_rate": 0.0,
                    "citations_union": [_c("https://reddit.com/r/ai/comments/pplx")],
                },
                "claude": {
                    "cited": False,
                    "citation_rate": 0.0,
                    "citations_union": [_c("https://quora.com/What-is-ai")],
                },
            },
        }],
    }
    (tmp_path / "citations-2026-05-01.json").write_text(json.dumps(data), encoding="utf-8")
    threads = find_top_threads(tmp_path, min_query_count=1)
    assert any("reddit" in t["url"] for t in threads)
    reddit_thread = next(t for t in threads if "reddit" in t["url"])
    assert "perplexity" in reddit_thread["engines"]
