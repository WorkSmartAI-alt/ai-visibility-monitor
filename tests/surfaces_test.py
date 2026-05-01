"""Tests for avm/surfaces.py — validates URL-to-surface categorization."""
import pytest
from avm.surfaces import categorize_url, surface_distribution, suggested_action

# Build a shared categories dict for speed (avoids file I/O per test)
from avm.surfaces import _build_categories
_CATS = _build_categories()


def cat(url: str) -> str:
    return categorize_url(url, _CATS)


# ── press ──────────────────────────────────────────────────────────────────────
def test_techcrunch():        assert cat("https://techcrunch.com/2026/01/ai-tools") == "press"
def test_forbes():            assert cat("https://www.forbes.com/sites/ai/2025") == "press"
def test_bloomberg():         assert cat("https://bloomberg.com/news/articles/ai") == "press"
def test_wired():             assert cat("https://wired.com/story/ai-search") == "press"
def test_venturebeat():       assert cat("https://venturebeat.com/ai/2026") == "press"
def test_inc():               assert cat("https://inc.com/ai-tools-guide") == "press"
def test_reuters():           assert cat("https://reuters.com/technology/ai") == "press"
def test_wsj():               assert cat("https://wsj.com/articles/ai-visibility") == "press"

# ── blog ───────────────────────────────────────────────────────────────────────
def test_medium():            assert cat("https://medium.com/@user/ai-post") == "blog"
def test_substack():          assert cat("https://newsletter.substack.com/p/ai") == "blog"
def test_devto():             assert cat("https://dev.to/ai-tools-2026") == "blog"
def test_hashnode():          assert cat("https://user.hashnode.dev/post") == "blog"

# ── forum ──────────────────────────────────────────────────────────────────────
def test_reddit():            assert cat("https://reddit.com/r/MachineLearning/comments/abc") == "forum"
def test_stackoverflow():     assert cat("https://stackoverflow.com/questions/1234") == "forum"
def test_quora():             assert cat("https://quora.com/What-is-AI-visibility") == "forum"
def test_hn():                assert cat("https://news.ycombinator.com/item?id=123") == "forum"
def test_stackexchange():     assert cat("https://ai.stackexchange.com/questions/1") == "forum"

# ── wikipedia ──────────────────────────────────────────────────────────────────
def test_wikipedia():         assert cat("https://en.wikipedia.org/wiki/Artificial_intelligence") == "wikipedia"
def test_wikidata():          assert cat("https://www.wikidata.org/entity/Q123") == "wikipedia"

# ── official_docs ──────────────────────────────────────────────────────────────
def test_anthropic_docs():    assert cat("https://docs.anthropic.com/claude/reference") == "official_docs"
def test_openai_platform():   assert cat("https://platform.openai.com/docs/api-reference") == "official_docs"
def test_google_dev():        assert cat("https://developers.google.com/ai") == "official_docs"

# ── github ─────────────────────────────────────────────────────────────────────
def test_github():            assert cat("https://github.com/anthropics/anthropic-sdk-python") == "github"
def test_github_raw():        assert cat("https://raw.githubusercontent.com/org/repo/README.md") == "uncategorized"

# ── linkedin ───────────────────────────────────────────────────────────────────
def test_linkedin_post():     assert cat("https://linkedin.com/posts/user_act1234") == "linkedin"
def test_linkedin_article():  assert cat("https://www.linkedin.com/pulse/ai-visibility-ignacio") == "linkedin"

# ── youtube ────────────────────────────────────────────────────────────────────
def test_youtube():           assert cat("https://youtube.com/watch?v=abc123") == "youtube"
def test_youtu_be():          assert cat("https://youtu.be/abc123") == "youtube"

# ── job_board ──────────────────────────────────────────────────────────────────
def test_indeed():            assert cat("https://indeed.com/jobs?q=ai+visibility") == "job_board"
def test_glassdoor():         assert cat("https://glassdoor.com/Reviews/company.htm") == "job_board"

# ── uncategorized ──────────────────────────────────────────────────────────────
def test_unknown_domain():    assert cat("https://obscure-niche-blog.io/ai-post") == "uncategorized"
def test_empty_url():         assert cat("") == "uncategorized"
def test_bad_url():           assert cat("not-a-url-at-all") == "uncategorized"

# ── surface_distribution ───────────────────────────────────────────────────────
def test_distribution_counts():
    citations = [
        {"url": "https://techcrunch.com/post"},
        {"url": "https://reddit.com/r/ai/comments/abc"},
        {"url": "https://reddit.com/r/ml/comments/xyz"},
        {"url": "https://medium.com/@user/post"},
    ]
    dist = surface_distribution(citations)
    assert dist["press"] == 1
    assert dist["forum"] == 2
    assert dist["blog"] == 1

def test_distribution_empty():
    assert surface_distribution([]) == {}

# ── suggested_action ───────────────────────────────────────────────────────────
def test_action_press_dominant():
    dist = {"press": 6, "blog": 1, "forum": 1}
    assert "HARO" in suggested_action(dist) or "press" in suggested_action(dist)

def test_action_forum_dominant():
    dist = {"forum": 5, "blog": 1}
    assert "subreddit" in suggested_action(dist) or "Q&A" in suggested_action(dist)

def test_action_balanced():
    dist = {"press": 2, "blog": 2, "forum": 2, "uncategorized": 2}
    assert "balanced" in suggested_action(dist)

def test_action_empty():
    assert "no citations" in suggested_action({})
