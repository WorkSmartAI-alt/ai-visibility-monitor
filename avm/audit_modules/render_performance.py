"""Category 4: Render Performance (15 points).

Fetches 3 sampled URLs with a Googlebot UA and checks for 200 responses
and evidence of server-side or pre-rendered content.
"""
from __future__ import annotations

from typing import Callable

MAX_POINTS: float = 15.0
GOOGLEBOT_UA = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)
# Threshold for inferring pre-rendered / SSR content
CONTENT_SIZE_THRESHOLD = 30_000


def audit(urls: list[str], fetch_fn: Callable[[str, str], dict]) -> dict:
    """Score render performance for sampled URLs fetched with Googlebot UA.

    Args:
        urls: Up to 3 URLs to check (home + 2 from sitemap).
        fetch_fn: Callable(url, ua) -> {status, ok, body, headers, size, error}.

    Returns structured audit result with per-URL detail and aggregate points.
    """
    fixes: list[dict] = []
    per_url: list[dict] = []
    points = 0.0

    for url in urls[:3]:
        result = fetch_fn(url, GOOGLEBOT_UA)
        status = result.get("status")
        ok = result.get("ok", False)
        headers = result.get("headers", {})
        size = result.get("size", 0)

        status_points = 3.0 if ok else 0.0

        prerender_header = headers.get("x-prerendered", "").lower() == "true"
        content_large = size > CONTENT_SIZE_THRESHOLD
        prerender_ok = prerender_header or content_large
        prerender_points = 2.0 if prerender_ok else 0.0

        points += status_points + prerender_points

        per_url.append({
            "url": url,
            "status": status,
            "ok": ok,
            "x_prerendered": prerender_header,
            "content_size": size,
            "content_large": content_large,
            "prerender_ok": prerender_ok,
            "error": result.get("error"),
        })

    if per_url:
        non_200 = [p["url"] for p in per_url if not p["ok"]]
        if non_200:
            fixes.append({
                "key": "fix_googlebot_non_200",
                "description": (
                    f"{len(non_200)} URL(s) returned non-200 with Googlebot UA "
                    f"({', '.join(u.split('/')[-1] or '/' for u in non_200[:2])})"
                ),
                "points_gained": len(non_200) * 3.0,
                "effort_minutes": 30,
            })

        not_prerendered = [p["url"] for p in per_url if p["ok"] and not p["prerender_ok"]]
        if not_prerendered:
            fixes.append({
                "key": "add_prerender",
                "description": (
                    "Add a pre-rendering layer (Prerender.io or SSR) so Googlebot "
                    "receives fully rendered HTML"
                ),
                "points_gained": len(not_prerendered) * 2.0,
                "effort_minutes": 120,
            })

    return {
        "points": round(points, 2),
        "max_points": MAX_POINTS,
        "per_url": per_url,
        "fixes": fixes,
    }
