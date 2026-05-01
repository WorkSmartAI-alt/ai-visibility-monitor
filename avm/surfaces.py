"""Source-surface categorization for cited URLs."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

SURFACE_CATEGORIES: dict[str, list[str]] = {
    "press": [
        "techcrunch.com", "forbes.com", "inc.com", "fastcompany.com",
        "wired.com", "venturebeat.com", "theverge.com", "bloomberg.com",
        "businessinsider.com", "wsj.com", "nytimes.com", "reuters.com",
        "axios.com", "marketwatch.com", "fortune.com", "theinformation.com",
        "cnbc.com", "apnews.com", "washingtonpost.com", "ft.com",
    ],
    "blog": [
        "medium.com", "substack.com", "hashnode.com", "hashnode.dev", "dev.to", "ghost.io",
        "wordpress.com", "blogger.com", "tumblr.com",
    ],
    "forum": [
        "reddit.com", "stackoverflow.com", "stackexchange.com", "quora.com",
        "news.ycombinator.com", "lobste.rs", "producthunt.com",
    ],
    "wikipedia": [
        "wikipedia.org", "wikidata.org", "wikimedia.org",
    ],
    "official_docs": [
        "support.claude.com", "docs.anthropic.com", "platform.openai.com",
        "developers.google.com", "docs.github.com", "developer.apple.com",
        "docs.microsoft.com", "learn.microsoft.com",
    ],
    "job_board": [
        "jobleads.com", "indeed.com", "glassdoor.com", "linkedin.com/jobs",
        "hired.com", "levels.fyi",
    ],
    "github": [
        "github.com",
    ],
    "linkedin": [
        "linkedin.com",
    ],
    "youtube": [
        "youtube.com", "youtu.be",
    ],
    "podcast": [
        "spotify.com/episode", "apple.co/podcast", "anchor.fm",
        "podcasts.apple.com",
    ],
}

# Maps surface → action copy
_SURFACE_ACTIONS: dict[str, str] = {
    "press": "pitch HARO/Qwoted, target press placements",
    "forum": "build authority in relevant subreddits and Q&A",
    "blog": "guest post or invest in your own blog",
    "official_docs": "hard surface to displace, deprioritize",
    "uncategorized": "long-tail / niche market, your own content can win",
    "github": "contribute to relevant repos, add README mentions",
    "linkedin": "publish LinkedIn articles, engage in comments",
    "youtube": "create video content or sponsor channels in your niche",
    "podcast": "pitch podcast appearances or sponsor relevant shows",
    "wikipedia": "hard surface to displace, deprioritize",
    "job_board": "deprioritize — not a buyer decision surface",
}


def _load_overrides() -> dict[str, list[str]]:
    p = Path("surfaces.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _build_categories() -> dict[str, list[str]]:
    cats = {k: list(v) for k, v in SURFACE_CATEGORIES.items()}
    for cat, patterns in _load_overrides().items():
        if cat in cats:
            cats[cat] = patterns + cats[cat]
        else:
            cats[cat] = patterns
    return cats


def categorize_url(url: str, _cats: dict[str, list[str]] | None = None) -> str:
    """Return the surface category for a URL. Returns 'uncategorized' if unknown."""
    if _cats is None:
        _cats = _build_categories()
    try:
        netloc = urlparse(url).netloc.lower()
        # strip www.
        domain = netloc.removeprefix("www.")
        path_part = urlparse(url).path.lower()
        full = domain + path_part
    except Exception:
        return "uncategorized"

    for category, patterns in _cats.items():
        if category == "uncategorized":
            continue
        for pattern in patterns:
            if pattern in full:
                return category
    return "uncategorized"


def surface_distribution(citations: list[dict]) -> dict[str, int]:
    """Count citations by surface category."""
    cats = _build_categories()
    counts: dict[str, int] = {}
    for c in citations:
        url = c.get("url", "")
        cat = categorize_url(url, cats)
        counts[cat] = counts.get(cat, 0) + 1
    return counts


def suggested_action(dist: dict[str, int]) -> str:
    """Return a strategic action string based on surface distribution."""
    total = sum(dist.values())
    if total == 0:
        return "no citations found — create content to establish a presence"

    fracs = {k: v / total for k, v in dist.items()}

    if fracs.get("press", 0) > 0.50:
        return _SURFACE_ACTIONS["press"]
    if fracs.get("forum", 0) > 0.40:
        return _SURFACE_ACTIONS["forum"]
    if fracs.get("blog", 0) > 0.40:
        return _SURFACE_ACTIONS["blog"]
    if fracs.get("official_docs", 0) > 0.30:
        return _SURFACE_ACTIONS["official_docs"]
    if fracs.get("uncategorized", 0) > 0.50:
        return _SURFACE_ACTIONS["uncategorized"]
    return "balanced surface, all-channel approach"
