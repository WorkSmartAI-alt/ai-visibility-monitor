"""Category 2: Discovery Files (15 points).

Checks llms.txt presence, sitemap freshness, and whether robots.txt
explicitly names AI bot UAs (signals deliberate configuration).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from avm.audit_modules.crawler_access import AI_BOT_UAS

MAX_POINTS: float = 15.0

_LASTMOD_RE = re.compile(r"<lastmod>\s*(\S+)\s*</lastmod>", re.IGNORECASE)


def _sitemap_is_fresh(http_last_modified: str | None, sitemap_body: str) -> bool:
    """Return True if sitemap was modified within the last 30 days."""
    now = datetime.now(timezone.utc)
    cutoff_days = 30

    # Try HTTP Last-Modified header first
    if http_last_modified:
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(http_last_modified)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (now - dt).days <= cutoff_days
        except Exception:
            pass

    # Fall back to most recent <lastmod> in sitemap body
    dates = _LASTMOD_RE.findall(sitemap_body)
    for d in sorted(dates, reverse=True):
        try:
            # Handle both "2025-01-15" and "2025-01-15T12:00:00+00:00"
            d_clean = d[:10]
            dt = datetime.strptime(d_clean, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return (now - dt).days <= cutoff_days
        except ValueError:
            continue

    return False


def _robots_mentions_ai_bots(robots_body: str, threshold: int = 5) -> int:
    """Count how many AI bot UAs are explicitly mentioned in robots.txt."""
    if not robots_body:
        return 0
    body_lower = robots_body.lower()
    return sum(1 for ua in AI_BOT_UAS if ua.lower() in body_lower)


def audit(
    llms_status: int | None,
    sitemap_status: int | None,
    sitemap_body: str,
    sitemap_last_modified: str | None,
    robots_body: str | None,
) -> dict:
    """Score discovery file presence.

    Args:
        llms_status: HTTP status code for /llms.txt (None if unreachable).
        sitemap_status: HTTP status code for sitemap.xml (None if unreachable).
        sitemap_body: Raw sitemap XML body (empty string if not fetched).
        sitemap_last_modified: Value of Last-Modified header from sitemap response.
        robots_body: Raw robots.txt body (None if not fetched).

    Returns structured audit result with points, max_points, and detail flags.
    """
    fixes: list[dict] = []

    # llms.txt present and returns 200
    llms_ok = llms_status == 200
    llms_points = 5.0 if llms_ok else 0.0
    if not llms_ok:
        fixes.append({
            "key": "add_llms_txt",
            "description": "Add /llms.txt to help AI engines understand your site content",
            "points_gained": 5.0,
            "effort_minutes": 30,
        })

    # sitemap.xml present, returns 200, and last-modified within 30 days
    sitemap_present = sitemap_status == 200
    sitemap_fresh = sitemap_present and _sitemap_is_fresh(sitemap_last_modified, sitemap_body)
    sitemap_stale = sitemap_present and not sitemap_fresh
    if sitemap_fresh:
        sitemap_points = 5.0
    elif sitemap_present:
        sitemap_points = 3.0  # partial credit: present but stale
        fixes.append({
            "key": "refresh_sitemap",
            "description": "Regenerate sitemap.xml (last-modified is over 30 days ago)",
            "points_gained": 2.0,
            "effort_minutes": 15,
        })
    else:
        sitemap_points = 0.0
        fixes.append({
            "key": "add_sitemap",
            "description": "Add sitemap.xml and submit it to Google Search Console",
            "points_gained": 5.0,
            "effort_minutes": 30,
        })

    # robots.txt explicitly mentions at least 5 AI bot UAs
    bot_mention_count = _robots_mentions_ai_bots(robots_body or "")
    robots_ua_ok = bot_mention_count >= 5
    robots_ua_points = 5.0 if robots_ua_ok else 0.0
    if not robots_ua_ok:
        needed = 5 - bot_mention_count
        fixes.append({
            "key": "robots_add_ai_bots",
            "description": (
                f"Add explicit AI bot rules to robots.txt "
                f"({bot_mention_count} of 5 required UAs mentioned, need {needed} more)"
            ),
            "points_gained": 5.0,
            "effort_minutes": 20,
        })

    points = llms_points + sitemap_points + robots_ua_points

    return {
        "points": round(points, 2),
        "max_points": MAX_POINTS,
        "llms_txt_present": llms_ok,
        "sitemap_present": sitemap_present,
        "sitemap_fresh": sitemap_fresh,
        "sitemap_stale": sitemap_stale,
        "robots_ai_bot_mentions": bot_mention_count,
        "robots_mentions_ai_bots": robots_ua_ok,
        "fixes": fixes,
    }
