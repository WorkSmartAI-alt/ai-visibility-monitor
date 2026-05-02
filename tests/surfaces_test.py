"""Tests for avm/surfaces.py — validates URL-to-surface categorization."""
import pytest
from avm.surfaces import (
    categorize_url, surface_distribution, suggested_action,
    get_parent_surface, parent_distribution, SURFACE_PARENTS,
    _build_categories,
)

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

# ── community sub-categories (new in v0.2.3) ───────────────────────────────────
def test_reddit():            assert cat("https://reddit.com/r/MachineLearning/comments/abc") == "reddit"
def test_reddit_old():        assert cat("https://old.reddit.com/r/consulting/comments/xyz") == "reddit"
def test_quora():             assert cat("https://quora.com/What-is-AI-visibility") == "quora"
def test_stackoverflow():     assert cat("https://stackoverflow.com/questions/1234") == "stackoverflow"
def test_stackexchange():     assert cat("https://ai.stackexchange.com/questions/1") == "stackexchange"
def test_hn():                assert cat("https://news.ycombinator.com/item?id=123") == "ycombinator"
def test_yc_main():           assert cat("https://ycombinator.com/companies/ai") == "ycombinator"
def test_g2():                assert cat("https://g2.com/products/claude/reviews") == "g2"
def test_trustpilot():        assert cat("https://trustpilot.com/review/anthropic.com") == "trustpilot"
def test_yelp():              assert cat("https://yelp.com/biz/ai-consulting-miami") == "yelp"
def test_glassdoor():         assert cat("https://glassdoor.com/Reviews/company-EI.htm") == "glassdoor"
def test_producthunt():       assert cat("https://producthunt.com/posts/ai-visibility-monitor") == "producthunt"

# ── forum (backward compat — lobste.rs only, others now in specific cats) ──────
def test_lobsters():          assert cat("https://lobste.rs/s/ai-tools") == "forum"

# ── wikipedia ──────────────────────────────────────────────────────────────────
def test_wikipedia():         assert cat("https://en.wikipedia.org/wiki/Artificial_intelligence") == "wikipedia"
def test_wikidata():          assert cat("https://www.wikidata.org/entity/Q123") == "wikipedia"

# ── official_docs ──────────────────────────────────────────────────────────────
def test_anthropic_docs():    assert cat("https://docs.anthropic.com/claude/reference") == "official_docs"
def test_openai_platform():   assert cat("https://platform.openai.com/docs/api-reference") == "official_docs"
def test_google_dev():        assert cat("https://developers.google.com/ai") == "official_docs"

# ── industry_news ──────────────────────────────────────────────────────────────
def test_prnewswire():        assert cat("https://prnewswire.com/news-releases/ai-2026.html") == "industry_news"
def test_businesswire():      assert cat("https://businesswire.com/news/home/ai-consulting") == "industry_news"
def test_constructiondive():  assert cat("https://constructiondive.com/news/ai-tools") == "industry_news"
def test_wealthmgmt():        assert cat("https://wealthmanagement.com/technology/ai") == "industry_news"

# ── consulting_competitors ─────────────────────────────────────────────────────
def test_headofai():          assert cat("https://headofai.ai/services") == "consulting_competitors"
def test_bosio():             assert cat("https://bosio.digital/ai-fractional") == "consulting_competitors"
def test_chiefaiofficer():    assert cat("https://chiefaiofficer.com/services") == "consulting_competitors"

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

# ── uncategorized ──────────────────────────────────────────────────────────────
def test_unknown_domain():    assert cat("https://obscure-niche-blog.io/ai-post") == "uncategorized"
def test_empty_url():         assert cat("") == "uncategorized"
def test_bad_url():           assert cat("not-a-url-at-all") == "uncategorized"

# ── get_parent_surface ──────────────────────────────────────────────────────────
def test_parent_reddit():         assert get_parent_surface("reddit") == "community"
def test_parent_quora():          assert get_parent_surface("quora") == "community"
def test_parent_stackoverflow():  assert get_parent_surface("stackoverflow") == "community"
def test_parent_stackexchange():  assert get_parent_surface("stackexchange") == "community"
def test_parent_ycombinator():    assert get_parent_surface("ycombinator") == "community"
def test_parent_g2():             assert get_parent_surface("g2") == "community"
def test_parent_trustpilot():     assert get_parent_surface("trustpilot") == "community"
def test_parent_glassdoor():      assert get_parent_surface("glassdoor") == "community"
def test_parent_producthunt():    assert get_parent_surface("producthunt") == "community"
def test_parent_forum():          assert get_parent_surface("forum") == "community"  # backward compat
def test_parent_press():          assert get_parent_surface("press") == "press"
def test_parent_blog():           assert get_parent_surface("blog") == "blog"
def test_parent_official_docs():  assert get_parent_surface("official_docs") == "official"
def test_parent_wikipedia():      assert get_parent_surface("wikipedia") == "official"
def test_parent_linkedin():       assert get_parent_surface("linkedin") == "social"
def test_parent_youtube():        assert get_parent_surface("youtube") == "social"
def test_parent_unknown():        assert get_parent_surface("made_up_category") == "other"

# ── parent_distribution rollup ─────────────────────────────────────────────────
def test_parent_distribution_rollup():
    leaf = {"reddit": 3, "quora": 2, "press": 4, "blog": 1}
    parent = parent_distribution(leaf)
    assert parent["community"] == 5
    assert parent["press"] == 4
    assert parent["blog"] == 1

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
    assert dist["reddit"] == 2
    assert dist["blog"] == 1

def test_distribution_empty():
    assert surface_distribution([]) == {}

# ── suggested_action ───────────────────────────────────────────────────────────
def test_action_press_dominant():
    dist = {"press": 6, "blog": 1, "reddit": 1}
    action = suggested_action(dist)
    assert "HARO" in action or "press" in action

def test_action_community_dominant():
    dist = {"reddit": 5, "quora": 2, "blog": 1}
    action = suggested_action(dist)
    assert "reddit" in action.lower() or "subreddit" in action.lower() or "community" in action.lower()

def test_action_balanced():
    dist = {"press": 2, "blog": 2, "reddit": 2, "uncategorized": 2}
    assert "balanced" in suggested_action(dist)

def test_action_empty():
    assert "no citations" in suggested_action({})
