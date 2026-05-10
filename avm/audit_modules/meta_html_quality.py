"""Category 5: Meta + HTML Quality (10 points).

Checks title length, meta description length, h1 count, and canonical
link presence across 3 sampled URLs.
"""
from __future__ import annotations

from urllib.parse import urlparse

from avm.audit_modules._html import PageData

MAX_POINTS: float = 10.0

TITLE_MIN = 30
TITLE_MAX = 65
DESC_MIN = 120
DESC_MAX = 160


def _canonical_matches(page: PageData) -> bool:
    if not page.canonical:
        return False
    try:
        canonical = urlparse(page.canonical)
        page_url = urlparse(page.url)
        # Compare scheme+netloc+path, ignoring trailing slash difference
        c_path = canonical.path.rstrip("/") or "/"
        p_path = page_url.path.rstrip("/") or "/"
        return (
            canonical.netloc.lower() == page_url.netloc.lower()
            and c_path == p_path
        )
    except Exception:
        return False


def audit(pages: list[PageData]) -> dict:
    """Score meta and HTML quality across sampled pages.

    Caps total at MAX_POINTS (10) even if arithmetic yields 10.5.

    Returns structured audit result with per-URL detail and fix suggestions.
    """
    fixes: list[dict] = []
    per_url: list[dict] = []

    title_pass = 0
    desc_pass = 0
    h1_pass = 0
    canonical_pass = 0

    bad_titles: list[str] = []
    bad_descs: list[str] = []
    bad_h1s: list[str] = []
    missing_canonicals: list[str] = []

    for page in pages:
        title_len = len(page.title or "")
        desc_len = len(page.description or "")
        h1_ok = page.h1_count == 1
        canonical_ok = _canonical_matches(page)

        title_ok = TITLE_MIN <= title_len <= TITLE_MAX
        desc_ok = DESC_MIN <= desc_len <= DESC_MAX

        if title_ok:
            title_pass += 1
        else:
            bad_titles.append(page.url)

        if desc_ok:
            desc_pass += 1
        else:
            bad_descs.append(page.url)

        if h1_ok:
            h1_pass += 1
        else:
            bad_h1s.append(page.url)

        if canonical_ok:
            canonical_pass += 1
        else:
            missing_canonicals.append(page.url)

        slug = urlparse(page.url).path or "/"
        per_url.append({
            "url": page.url,
            "slug": slug,
            "title_len": title_len,
            "title_ok": title_ok,
            "desc_len": desc_len,
            "desc_ok": desc_ok,
            "h1_count": page.h1_count,
            "h1_ok": h1_ok,
            "canonical": page.canonical,
            "canonical_ok": canonical_ok,
        })

    n = len(pages)
    if n == 0:
        return {
            "points": 0.0,
            "max_points": MAX_POINTS,
            "per_url": [],
            "fixes": [],
        }

    raw_points = (
        title_pass * 1.0
        + desc_pass * 1.0
        + h1_pass * 1.0
        + canonical_pass * 0.5
    )
    points = min(raw_points, MAX_POINTS)

    if bad_titles:
        slugs = ", ".join(urlparse(u).path or "/" for u in bad_titles[:3])
        fixes.append({
            "key": "fix_title_length",
            "description": (
                f"Adjust title length to 30-65 chars on: {slugs}"
            ),
            "points_gained": float(len(bad_titles)),
            "effort_minutes": 20,
        })

    if bad_descs:
        slugs = ", ".join(urlparse(u).path or "/" for u in bad_descs[:3])
        fixes.append({
            "key": "fix_meta_description",
            "description": (
                f"Write meta descriptions of 120-160 chars on: {slugs}"
            ),
            "points_gained": float(len(bad_descs)),
            "effort_minutes": 30,
        })

    if bad_h1s:
        slugs = ", ".join(urlparse(u).path or "/" for u in bad_h1s[:3])
        fixes.append({
            "key": "fix_h1",
            "description": (
                f"Ensure exactly one H1 per page on: {slugs}"
            ),
            "points_gained": float(len(bad_h1s)),
            "effort_minutes": 20,
        })

    if missing_canonicals:
        slugs = ", ".join(urlparse(u).path or "/" for u in missing_canonicals[:3])
        fixes.append({
            "key": "add_canonical",
            "description": (
                f"Add canonical link matching page URL on: {slugs}"
            ),
            "points_gained": len(missing_canonicals) * 0.5,
            "effort_minutes": 15,
        })

    return {
        "points": round(points, 2),
        "max_points": MAX_POINTS,
        "per_url": per_url,
        "title_pass": title_pass,
        "desc_pass": desc_pass,
        "h1_pass": h1_pass,
        "canonical_pass": canonical_pass,
        "fixes": fixes,
    }
