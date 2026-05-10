"""Category 3: Schema Markup (20 points).

Parses JSON-LD blocks from sampled pages and checks for four
schema types that aid AI engine comprehension.
"""
from __future__ import annotations

from avm.audit_modules._html import PageData

MAX_POINTS: float = 20.0


def _all_types(block: dict) -> list[str]:
    """Return all @type values from a JSON-LD block, including @graph entries."""
    types: list[str] = []
    raw = block.get("@type")
    if isinstance(raw, str):
        types.append(raw)
    elif isinstance(raw, list):
        types.extend(t for t in raw if isinstance(t, str))

    for item in block.get("@graph", []):
        if isinstance(item, dict):
            types.extend(_all_types(item))
    return types


def _has_service_schema(blocks: list[dict]) -> bool:
    required = {"name", "description", "areaserved", "provider"}
    for block in blocks:
        types = [t.lower() for t in _all_types(block)]
        if "service" not in types:
            continue
        keys = {k.lower() for k in block.keys()}
        if required.issubset(keys):
            return True
    return False


def _has_faq_schema(blocks: list[dict]) -> bool:
    for block in blocks:
        types = [t.lower() for t in _all_types(block)]
        if "faqpage" not in types:
            continue
        entries = block.get("mainEntity", block.get("mainentity", []))
        if isinstance(entries, list) and len(entries) >= 5:
            return True
    return False


def _has_article_schema(blocks: list[dict]) -> bool:
    article_types = {"article", "blogposting", "newsarticle", "technicalarticle"}
    for block in blocks:
        types = [t.lower() for t in _all_types(block)]
        if any(t in article_types for t in types):
            return True
    return False


def _has_breadcrumb_schema(blocks: list[dict]) -> bool:
    for block in blocks:
        types = [t.lower() for t in _all_types(block)]
        if "breadcrumblist" in types:
            return True
    return False


def audit(pages: list[PageData]) -> dict:
    """Score schema markup across sampled pages.

    Args:
        pages: Parsed page data from sampled URLs.

    Returns structured audit result with points, flags, and fix suggestions.
    """
    fixes: list[dict] = []
    blog_urls = [p.url for p in pages if any(
        seg in p.url for seg in ("/blog/", "/post/", "/article/", "/articles/", "/news/")
    )]

    # Collect all JSON-LD blocks per page for per-type checks
    all_blocks: list[dict] = []
    for page in pages:
        all_blocks.extend(page.json_ld_blocks)

    blog_blocks: list[dict] = []
    for page in pages:
        if any(seg in page.url for seg in ("/blog/", "/post/", "/article/", "/articles/", "/news/")):
            blog_blocks.extend(page.json_ld_blocks)

    has_service = _has_service_schema(all_blocks)
    has_faq = _has_faq_schema(all_blocks)
    has_article = _has_article_schema(blog_blocks) if blog_urls else None
    has_breadcrumb = _has_breadcrumb_schema(all_blocks)

    points = 0.0

    service_points = 5.0 if has_service else 0.0
    points += service_points
    if not has_service:
        fixes.append({
            "key": "add_service_schema",
            "description": "Add Service schema (name, description, areaServed, provider) to service pages",
            "points_gained": 5.0,
            "effort_minutes": 60,
        })

    faq_points = 5.0 if has_faq else 0.0
    points += faq_points
    if not has_faq:
        fixes.append({
            "key": "add_faq_schema",
            "description": "Add FAQPage schema with 5+ Q&As to key landing pages",
            "points_gained": 5.0,
            "effort_minutes": 90,
        })

    # Article schema only scored/penalized if blog URLs were found in sample
    if has_article is None:
        article_points = 0.0  # no blog URLs in sample, skip
        article_note = "no blog URLs in sample"
    elif has_article:
        article_points = 5.0
        article_note = "found"
    else:
        article_points = 0.0
        article_note = "missing"
        fixes.append({
            "key": "add_article_schema",
            "description": "Add Article (or BlogPosting) schema to blog posts",
            "points_gained": 5.0,
            "effort_minutes": 45,
        })
    points += article_points

    breadcrumb_points = 5.0 if has_breadcrumb else 0.0
    points += breadcrumb_points
    if not has_breadcrumb:
        fixes.append({
            "key": "add_breadcrumb_schema",
            "description": "Add BreadcrumbList schema to interior pages",
            "points_gained": 5.0,
            "effort_minutes": 30,
        })

    # Max points is 20 when blog URLs are in sample, 15 when not
    effective_max = 20.0 if has_article is not None else 15.0

    return {
        "points": round(points, 2),
        "max_points": effective_max,
        "has_service_schema": has_service,
        "has_faq_schema": has_faq,
        "has_article_schema": has_article,
        "has_breadcrumb_schema": has_breadcrumb,
        "blog_urls_sampled": blog_urls,
        "article_note": article_note,
        "fixes": fixes,
    }
