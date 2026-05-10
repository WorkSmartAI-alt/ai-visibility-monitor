"""Category 6: Open Graph + Social (10 points).

Checks og:title, og:description, og:image (and reachability), og:type,
and twitter:card across 3 sampled URLs. Final score is the average
per-page score rounded to the category max of 10.
"""
from __future__ import annotations

from typing import Callable
from urllib.parse import urlparse

from avm.audit_modules._html import PageData

MAX_POINTS: float = 10.0
POINTS_PER_ELEMENT: float = 2.0
OG_ELEMENTS = ("og:title", "og:description", "og:image", "og:type")


def _score_page(page: PageData, image_reachable: bool) -> dict:
    og = page.og
    has_og_title = bool(og.get("og:title"))
    has_og_desc = bool(og.get("og:description"))
    has_og_image = bool(og.get("og:image")) and image_reachable
    has_og_type = bool(og.get("og:type"))
    has_twitter = bool(page.twitter_card)

    score = sum([
        POINTS_PER_ELEMENT if has_og_title else 0,
        POINTS_PER_ELEMENT if has_og_desc else 0,
        POINTS_PER_ELEMENT if has_og_image else 0,
        POINTS_PER_ELEMENT if has_og_type else 0,
        POINTS_PER_ELEMENT if has_twitter else 0,
    ])

    return {
        "url": page.url,
        "slug": urlparse(page.url).path or "/",
        "og_title": has_og_title,
        "og_description": has_og_desc,
        "og_image": bool(og.get("og:image")),
        "og_image_url": og.get("og:image"),
        "og_image_reachable": image_reachable,
        "og_type": has_og_type,
        "twitter_card": has_twitter,
        "page_score": score,
    }


def audit(pages: list[PageData], fetch_fn: Callable[[str, str], dict]) -> dict:
    """Score Open Graph and Twitter Card coverage across sampled pages.

    Checks og:image reachability with a HEAD request.
    Final score is the average per-page score, capped at MAX_POINTS (10).

    Args:
        pages: Parsed page data from sampled URLs.
        fetch_fn: Callable(url, ua) -> {status, ok, ...}.
    """
    fixes: list[dict] = []
    per_url: list[dict] = []

    missing_og_image: list[str] = []
    missing_og_title: list[str] = []
    missing_og_desc: list[str] = []
    missing_og_type: list[str] = []
    missing_twitter: list[str] = []

    for page in pages:
        image_url = page.og.get("og:image", "")
        image_reachable = False
        if image_url:
            try:
                r = fetch_fn(image_url, None)
                image_reachable = r.get("ok", False)
            except Exception:
                image_reachable = False

        scored = _score_page(page, image_reachable)
        per_url.append(scored)

        slug = urlparse(page.url).path or "/"
        if not scored["og_title"]:
            missing_og_title.append(slug)
        if not scored["og_description"]:
            missing_og_desc.append(slug)
        if not (scored["og_image"] and scored["og_image_reachable"]):
            missing_og_image.append(slug)
        if not scored["og_type"]:
            missing_og_type.append(slug)
        if not scored["twitter_card"]:
            missing_twitter.append(slug)

    if not per_url:
        return {"points": 0.0, "max_points": MAX_POINTS, "per_url": [], "fixes": []}

    avg_score = sum(p["page_score"] for p in per_url) / len(per_url)
    points = min(round(avg_score, 2), MAX_POINTS)

    if missing_og_image:
        fixes.append({
            "key": "add_og_image",
            "description": (
                f"Add og:image to: {', '.join(missing_og_image[:3])}"
            ),
            "points_gained": round(len(missing_og_image) / len(per_url) * POINTS_PER_ELEMENT, 2),
            "effort_minutes": 30,
        })
    if missing_twitter:
        fixes.append({
            "key": "add_twitter_card",
            "description": (
                f"Add <meta name='twitter:card'> to: {', '.join(missing_twitter[:3])}"
            ),
            "points_gained": round(len(missing_twitter) / len(per_url) * POINTS_PER_ELEMENT, 2),
            "effort_minutes": 15,
        })
    if missing_og_title:
        fixes.append({
            "key": "add_og_title",
            "description": (
                f"Add og:title to: {', '.join(missing_og_title[:3])}"
            ),
            "points_gained": round(len(missing_og_title) / len(per_url) * POINTS_PER_ELEMENT, 2),
            "effort_minutes": 15,
        })
    if missing_og_desc:
        fixes.append({
            "key": "add_og_description",
            "description": (
                f"Add og:description to: {', '.join(missing_og_desc[:3])}"
            ),
            "points_gained": round(len(missing_og_desc) / len(per_url) * POINTS_PER_ELEMENT, 2),
            "effort_minutes": 15,
        })

    return {
        "points": points,
        "max_points": MAX_POINTS,
        "per_url": per_url,
        "fixes": fixes,
    }
