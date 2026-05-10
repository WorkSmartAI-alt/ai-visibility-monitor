"""Tests for avm audit-prospect modules and orchestrator."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from avm.audit_modules._html import PageData, parse_page
from avm.audit_modules import crawler_access, discovery_files, meta_html_quality, og_social, render_performance, schema_markup


# ---------------------------------------------------------------------------
# Category 1: Crawler Accessibility
# ---------------------------------------------------------------------------

ROBOTS_BLOCKS_ALL = """
User-agent: *
Disallow: /
"""

ROBOTS_ALLOWS_ALL = """
User-agent: *
Allow: /
Disallow:
"""

ROBOTS_EXPLICIT_AI = """
User-agent: GPTBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: *
Allow: /
"""

ROBOTS_SELECTIVE_BLOCK = """
User-agent: *
Allow: /

User-agent: GPTBot
Disallow: /
"""


def test_crawler_all_accessible_when_robots_missing():
    # No robots.txt = no blocking rules = all bots accessible (protocol default)
    result = crawler_access.audit(None)
    assert result["points"] == pytest.approx(30.0)
    assert result["blocked_uas"] == []
    assert result.get("robots_missing") is True


def test_crawler_full_score_when_wildcard_allows():
    result = crawler_access.audit(ROBOTS_ALLOWS_ALL)
    assert result["points"] == pytest.approx(30.0)
    assert result["blocked_uas"] == []


def test_crawler_zero_when_wildcard_blocks_all():
    result = crawler_access.audit(ROBOTS_BLOCKS_ALL)
    assert result["points"] == 0.0
    assert len(result["blocked_uas"]) == len(crawler_access.AI_BOT_UAS)


def test_crawler_explicit_ua_overrides_wildcard():
    # GPTBot is explicitly blocked, but wildcard allows
    result = crawler_access.audit(ROBOTS_SELECTIVE_BLOCK)
    blocked = result["blocked_uas"]
    assert "GPTBot" in blocked
    # All others should be accessible (wildcard Allow: /)
    assert "ClaudeBot" not in blocked


def test_crawler_explicit_allow_wins():
    result = crawler_access.audit(ROBOTS_EXPLICIT_AI)
    assert result["points"] == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# Category 2: Discovery Files
# ---------------------------------------------------------------------------

SITEMAP_FRESH = """<?xml version="1.0"?>
<urlset>
  <url><loc>https://example.com/</loc><lastmod>2026-04-30</lastmod></url>
</urlset>
"""

SITEMAP_STALE = """<?xml version="1.0"?>
<urlset>
  <url><loc>https://example.com/</loc><lastmod>2025-01-01</lastmod></url>
</urlset>
"""

ROBOTS_MENTIONS_5_BOTS = "\n".join(
    f"User-agent: {ua}\nAllow: /" for ua in crawler_access.AI_BOT_UAS[:5]
)


def test_discovery_full_score():
    result = discovery_files.audit(
        llms_status=200,
        sitemap_status=200,
        sitemap_body=SITEMAP_FRESH,
        sitemap_last_modified=None,
        robots_body=ROBOTS_MENTIONS_5_BOTS,
    )
    assert result["points"] == pytest.approx(15.0)
    assert result["llms_txt_present"] is True
    assert result["sitemap_fresh"] is True
    assert result["robots_mentions_ai_bots"] is True


def test_discovery_stale_sitemap_partial_credit():
    result = discovery_files.audit(
        llms_status=200,
        sitemap_status=200,
        sitemap_body=SITEMAP_STALE,
        sitemap_last_modified=None,
        robots_body=ROBOTS_MENTIONS_5_BOTS,
    )
    assert result["sitemap_stale"] is True
    # Partial credit (3 pts) + llms (5) + bots (5) = 13
    assert result["points"] == pytest.approx(13.0)


def test_discovery_zero_when_all_missing():
    result = discovery_files.audit(
        llms_status=404,
        sitemap_status=404,
        sitemap_body="",
        sitemap_last_modified=None,
        robots_body="",
    )
    assert result["points"] == pytest.approx(0.0)
    assert len(result["fixes"]) > 0


def test_discovery_robots_bot_count():
    result = discovery_files.audit(
        llms_status=404,
        sitemap_status=404,
        sitemap_body="",
        sitemap_last_modified=None,
        robots_body="\n".join(
            f"User-agent: {ua}\nAllow: /" for ua in crawler_access.AI_BOT_UAS[:3]
        ),
    )
    assert result["robots_ai_bot_mentions"] == 3
    assert result["robots_mentions_ai_bots"] is False


# ---------------------------------------------------------------------------
# Category 3: Schema Markup
# ---------------------------------------------------------------------------

SERVICE_SCHEMA_HTML = """
<html><body>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Service",
  "name": "AI Consulting",
  "description": "Fractional Head of AI",
  "areaServed": "US",
  "provider": {"@type": "Organization", "name": "Work-Smart.ai"}
}
</script>
</body></html>
"""

FAQ_SCHEMA_HTML = """
<html><body>
<script type="application/ld+json">
{
  "@type": "FAQPage",
  "mainEntity": [
    {"@type": "Question", "name": "Q1", "acceptedAnswer": {"text": "A1"}},
    {"@type": "Question", "name": "Q2", "acceptedAnswer": {"text": "A2"}},
    {"@type": "Question", "name": "Q3", "acceptedAnswer": {"text": "A3"}},
    {"@type": "Question", "name": "Q4", "acceptedAnswer": {"text": "A4"}},
    {"@type": "Question", "name": "Q5", "acceptedAnswer": {"text": "A5"}}
  ]
}
</script>
</body></html>
"""

ARTICLE_SCHEMA_HTML = """
<html><body>
<script type="application/ld+json">
{"@type": "BlogPosting", "headline": "Test", "datePublished": "2026-01-01"}
</script>
</body></html>
"""

BREADCRUMB_SCHEMA_HTML = """
<html><body>
<script type="application/ld+json">
{"@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": 1}]}
</script>
</body></html>
"""


def test_schema_service_schema_detected():
    pages = [parse_page("https://example.com/", SERVICE_SCHEMA_HTML)]
    result = schema_markup.audit(pages)
    assert result["has_service_schema"] is True
    assert result["points"] >= 5.0


def test_schema_faq_requires_5_qas():
    pages = [parse_page("https://example.com/", FAQ_SCHEMA_HTML)]
    result = schema_markup.audit(pages)
    assert result["has_faq_schema"] is True


def test_schema_article_on_blog_url():
    pages = [parse_page("https://example.com/blog/post-1", ARTICLE_SCHEMA_HTML)]
    result = schema_markup.audit(pages)
    assert result["has_article_schema"] is True
    assert "https://example.com/blog/post-1" in result["blog_urls_sampled"]


def test_schema_article_not_scored_without_blog_url():
    pages = [parse_page("https://example.com/services", ARTICLE_SCHEMA_HTML)]
    result = schema_markup.audit(pages)
    assert result["has_article_schema"] is None  # no blog URL in sample


def test_schema_breadcrumb_detected():
    pages = [parse_page("https://example.com/about", BREADCRUMB_SCHEMA_HTML)]
    result = schema_markup.audit(pages)
    assert result["has_breadcrumb_schema"] is True


def test_schema_full_score():
    pages = [
        parse_page("https://example.com/", SERVICE_SCHEMA_HTML),
        parse_page("https://example.com/faq", FAQ_SCHEMA_HTML),
        parse_page("https://example.com/blog/post", ARTICLE_SCHEMA_HTML),
        parse_page("https://example.com/about", BREADCRUMB_SCHEMA_HTML),
    ]
    result = schema_markup.audit(pages)
    assert result["points"] == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# Category 4: Render Performance
# ---------------------------------------------------------------------------

def _mock_fetch_200_prerendered(url: str, ua: str) -> dict:
    return {
        "status": 200, "ok": True, "body": "x" * 50_000,
        "headers": {"x-prerendered": "true"}, "size": 50_000, "error": None,
    }


def _mock_fetch_200_large(url: str, ua: str) -> dict:
    return {
        "status": 200, "ok": True, "body": "x" * 35_000,
        "headers": {}, "size": 35_000, "error": None,
    }


def _mock_fetch_404(url: str, ua: str) -> dict:
    return {
        "status": 404, "ok": False, "body": "", "headers": {}, "size": 0, "error": "HTTPError 404",
    }


def test_render_full_score_prerendered():
    result = render_performance.audit(
        ["https://example.com/", "https://example.com/about", "https://example.com/services"],
        _mock_fetch_200_prerendered,
    )
    assert result["points"] == pytest.approx(15.0)


def test_render_full_score_large_content():
    result = render_performance.audit(
        ["https://example.com/", "https://example.com/about", "https://example.com/services"],
        _mock_fetch_200_large,
    )
    assert result["points"] == pytest.approx(15.0)


def test_render_zero_on_all_404():
    result = render_performance.audit(
        ["https://example.com/", "https://example.com/about"],
        _mock_fetch_404,
    )
    assert result["points"] == pytest.approx(0.0)
    assert len(result["fixes"]) > 0


# ---------------------------------------------------------------------------
# Category 5: Meta + HTML Quality
# ---------------------------------------------------------------------------

GOOD_META_HTML = """
<html><head>
<title>AI Consulting for Growing Companies | Work-Smart.ai</title>
<meta name="description" content="Work-Smart.ai helps mid-size companies cut manual work with custom AI tools. No SaaS, no lock-in. Fractional Head of AI for hire. Based in Miami.">
<link rel="canonical" href="https://example.com/">
</head><body><h1>AI Consulting</h1></body></html>
"""

BAD_META_HTML = """
<html><head>
<title>Home</title>
<meta name="description" content="Short desc">
</head><body><h1>Title 1</h1><h1>Title 2</h1></body></html>
"""


def test_meta_full_score():
    pages = [parse_page("https://example.com/", GOOD_META_HTML)]
    result = meta_html_quality.audit(pages)
    # title OK (len > 30 and < 65), desc OK (>120, <160), h1=1, canonical matches
    assert result["title_pass"] == 1
    assert result["desc_pass"] == 1
    assert result["h1_pass"] == 1
    assert result["canonical_pass"] == 1
    assert result["points"] == pytest.approx(3.5)


def test_meta_bad_title_and_multiple_h1():
    pages = [parse_page("https://example.com/", BAD_META_HTML)]
    result = meta_html_quality.audit(pages)
    assert result["title_pass"] == 0  # "Home" is 4 chars, under 30
    assert result["h1_pass"] == 0     # 2 h1 tags


def test_meta_caps_at_10():
    # Even if 3 pages all pass everything, max is 10
    pages = [
        parse_page("https://example.com/", GOOD_META_HTML),
        parse_page("https://example.com/about", GOOD_META_HTML),
        parse_page("https://example.com/services", GOOD_META_HTML),
    ]
    result = meta_html_quality.audit(pages)
    assert result["points"] <= 10.0


def test_meta_empty_pages():
    result = meta_html_quality.audit([])
    assert result["points"] == 0.0


# ---------------------------------------------------------------------------
# Category 6: Open Graph + Social
# ---------------------------------------------------------------------------

OG_FULL_HTML = """
<html><head>
<meta property="og:title" content="Test Title">
<meta property="og:description" content="Test Description">
<meta property="og:image" content="https://example.com/og.png">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
</head><body></body></html>
"""

OG_MISSING_HTML = """
<html><head>
<meta property="og:title" content="Title only">
</head><body></body></html>
"""


def _fetch_image_ok(url: str, ua) -> dict:
    return {"ok": True, "status": 200}


def _fetch_image_fail(url: str, ua) -> dict:
    return {"ok": False, "status": 404}


def test_og_full_score():
    pages = [parse_page("https://example.com/", OG_FULL_HTML)]
    result = og_social.audit(pages, _fetch_image_ok)
    assert result["points"] == pytest.approx(10.0)


def test_og_missing_elements():
    pages = [parse_page("https://example.com/", OG_MISSING_HTML)]
    result = og_social.audit(pages, _fetch_image_fail)
    assert result["points"] == pytest.approx(2.0)  # only og:title present


def test_og_image_unreachable_not_counted():
    pages = [parse_page("https://example.com/", OG_FULL_HTML)]
    result = og_social.audit(pages, _fetch_image_fail)
    # og:image present but unreachable: 8 points (all except og:image)
    assert result["points"] == pytest.approx(8.0)


def test_og_empty_pages():
    result = og_social.audit([], _fetch_image_ok)
    assert result["points"] == 0.0


# ---------------------------------------------------------------------------
# HTML parser
# ---------------------------------------------------------------------------

def test_html_parser_extracts_title():
    page = parse_page("https://example.com/", "<html><head><title>  My Title  </title></head></html>")
    assert page.title == "My Title"


def test_html_parser_extracts_jsonld():
    page = parse_page("https://example.com/", """
    <html><head>
    <script type="application/ld+json">{"@type": "Service", "name": "Test"}</script>
    </head></html>
    """)
    assert len(page.json_ld_blocks) == 1
    assert page.json_ld_blocks[0]["@type"] == "Service"


def test_html_parser_counts_h1():
    page = parse_page("https://example.com/", "<html><body><h1>A</h1><h1>B</h1></body></html>")
    assert page.h1_count == 2


# ---------------------------------------------------------------------------
# End-to-end: live site (work-smart.ai) -- scores non-zero
# ---------------------------------------------------------------------------

@pytest.mark.live
def test_e2e_work_smart_ai_nonzero():
    from avm.audit_prospect import run_audit
    result = run_audit("https://work-smart.ai", timeout=10)
    assert result["score"] > 0
    assert result["grade"] in ("A", "B", "C", "D", "F")
    assert "categories" in result
    assert len(result.get("top_fixes", [])) <= 3
