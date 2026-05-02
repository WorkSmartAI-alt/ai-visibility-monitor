"""Source-surface categorization for cited URLs."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

# ── Primary surface categories ────────────────────────────────────────────────
# NOTE: individual community sub-categories (reddit, quora, etc.) replace the
# old "forum" bucket for new data. "forum" is kept for backward compatibility
# with existing JSON that may reference it; it maps to "community" via
# SURFACE_PARENTS. New citations will NOT land in "forum" — they'll match one
# of the more specific community sub-categories first.

SURFACE_CATEGORIES: dict[str, list[str]] = {
    # ── Press ────────────────────────────────────────────────────────────────
    "press": [
        "techcrunch.com", "forbes.com", "inc.com", "fastcompany.com",
        "wired.com", "venturebeat.com", "theverge.com", "bloomberg.com",
        "businessinsider.com", "wsj.com", "nytimes.com", "reuters.com",
        "axios.com", "marketwatch.com", "fortune.com", "theinformation.com",
        "cnbc.com", "apnews.com", "washingtonpost.com", "ft.com",
        "entrepreneur.com", "hbr.org",
    ],
    # ── Blog / owned media ───────────────────────────────────────────────────
    "blog": [
        "medium.com", "substack.com", "hashnode.com", "hashnode.dev", "dev.to",
        "ghost.io", "wordpress.com", "blogger.com", "tumblr.com",
    ],
    # ── Community sub-categories (replaces coarse "forum") ───────────────────
    "reddit": ["reddit.com"],
    "quora": ["quora.com"],
    "stackoverflow": ["stackoverflow.com"],
    "stackexchange": ["stackexchange.com"],
    "ycombinator": ["news.ycombinator.com", "ycombinator.com"],
    "g2": ["g2.com"],
    "trustpilot": ["trustpilot.com"],
    "yelp": ["yelp.com"],
    "glassdoor": ["glassdoor.com"],
    "producthunt": ["producthunt.com"],
    # ── Forum (backward-compat alias — matched last so specifics win) ─────────
    "forum": ["lobste.rs"],
    # ── Reference ────────────────────────────────────────────────────────────
    "wikipedia": ["wikipedia.org", "wikidata.org", "wikimedia.org"],
    # ── Official docs ────────────────────────────────────────────────────────
    "official_docs": [
        "support.claude.com", "docs.anthropic.com", "platform.openai.com",
        "developers.google.com", "docs.github.com", "developer.apple.com",
        "docs.microsoft.com", "learn.microsoft.com",
    ],
    # ── Job boards ───────────────────────────────────────────────────────────
    "job_board": [
        "jobleads.com", "indeed.com", "linkedin.com/jobs",
        "hired.com", "levels.fyi",
    ],
    # ── Social + media ───────────────────────────────────────────────────────
    "github": ["github.com"],
    "linkedin": ["linkedin.com"],
    "youtube": ["youtube.com", "youtu.be"],
    "podcast": [
        "spotify.com/episode", "apple.co/podcast", "anchor.fm",
        "podcasts.apple.com",
    ],
    # ── Industry-specific (AI consulting / mid-market) ────────────────────────
    "consulting_competitors": [
        "chiefaiofficer.com", "headofai.ai", "fastdatascience.com",
        "bosio.digital", "fayedigital.com", "amplifying-ai.com", "findskill.ai",
        "withjarvis.com", "aiforecast.ai",
    ],
    "industry_news": [
        "prnewswire.com", "businesswire.com", "globenewswire.com",
        "familywealthreport.com", "wealthsolutionsreport.com",
        "wealthmanagement.com", "fintrx.com", "masttro.com",
        "constructiondive.com", "constructionexec.com", "enr.com",
        "abajournal.com", "law.com",
    ],
}

# ── Parent grouping ───────────────────────────────────────────────────────────
# Maps parent bucket → list of leaf surface categories.
# Used for rollup reporting and baseline comparisons.

SURFACE_PARENTS: dict[str, list[str]] = {
    "community": [
        "reddit", "quora", "stackoverflow", "stackexchange", "ycombinator",
        "g2", "trustpilot", "yelp", "glassdoor", "producthunt",
        "forum",  # backward-compat: old "forum" citations roll up to community
    ],
    "press": ["press", "industry_news"],
    "official": ["official_docs", "wikipedia"],
    "blog": ["blog"],
    "social": ["linkedin", "youtube", "podcast", "github"],
    "competitor": ["consulting_competitors"],
    "other": ["job_board", "uncategorized"],
}

# Reverse lookup: leaf → parent
_LEAF_TO_PARENT: dict[str, str] = {
    leaf: parent
    for parent, leaves in SURFACE_PARENTS.items()
    for leaf in leaves
}


def get_parent_surface(category: str) -> str:
    """Return the parent surface bucket for a leaf category, or 'other'."""
    return _LEAF_TO_PARENT.get(category, "other")


# ── Action copy ───────────────────────────────────────────────────────────────
_SURFACE_ACTIONS: dict[str, str] = {
    "press": "pitch HARO/Qwoted, target press placements",
    "industry_news": "issue a press release, pitch trade publications",
    "community": "build authority in relevant subreddits and Q&A threads",
    "forum": "build authority in relevant subreddits and Q&A",
    "reddit": "engage in relevant subreddits — comment under your own account",
    "quora": "answer relevant Quora questions from your account",
    "stackoverflow": "answer technical questions, earn upvotes in your niche",
    "stackexchange": "answer relevant Stack Exchange questions",
    "ycombinator": "engage on HN — posts and comments in relevant threads",
    "g2": "request reviews from customers on G2",
    "trustpilot": "request reviews from customers on Trustpilot",
    "producthunt": "launch or update your Product Hunt listing",
    "blog": "guest post or invest in your own blog",
    "official_docs": "hard surface to displace, deprioritize",
    "wikipedia": "hard surface to displace, deprioritize",
    "uncategorized": "long-tail / niche market, your own content can win",
    "consulting_competitors": "competitor surface — monitor and outperform on content quality",
    "github": "contribute to relevant repos, add README mentions",
    "linkedin": "publish LinkedIn articles, engage in comments",
    "youtube": "create video content or sponsor channels in your niche",
    "podcast": "pitch podcast appearances or sponsor relevant shows",
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
    """Count citations by surface category (leaf-level)."""
    cats = _build_categories()
    counts: dict[str, int] = {}
    for c in citations:
        url = c.get("url", "")
        cat = categorize_url(url, cats)
        counts[cat] = counts.get(cat, 0) + 1
    return counts


def parent_distribution(leaf_dist: dict[str, int]) -> dict[str, int]:
    """Roll up a leaf-level distribution to parent buckets."""
    result: dict[str, int] = {}
    for leaf, count in leaf_dist.items():
        parent = get_parent_surface(leaf)
        result[parent] = result.get(parent, 0) + count
    return result


def suggested_action(dist: dict[str, int]) -> str:
    """Return a strategic action string based on surface distribution."""
    total = sum(dist.values())
    if total == 0:
        return "no citations found — create content to establish a presence"

    fracs = {k: v / total for k, v in dist.items()}

    # Use parent-level fractions for top-level strategy
    parent_dist = parent_distribution(dist)
    parent_total = sum(parent_dist.values())
    parent_fracs = {k: v / parent_total for k, v in parent_dist.items()} if parent_total else {}

    if fracs.get("press", 0) + fracs.get("industry_news", 0) > 0.50:
        return _SURFACE_ACTIONS["press"]
    if parent_fracs.get("community", 0) > 0.40:
        # Surface the most prominent community sub-category
        top_community = max(
            (c for c in ["reddit", "quora", "stackoverflow", "ycombinator", "forum"] if c in fracs),
            key=lambda c: fracs.get(c, 0),
            default="reddit",
        )
        return _SURFACE_ACTIONS.get(top_community, _SURFACE_ACTIONS["community"])
    if fracs.get("blog", 0) > 0.40:
        return _SURFACE_ACTIONS["blog"]
    if fracs.get("official_docs", 0) > 0.30:
        return _SURFACE_ACTIONS["official_docs"]
    if fracs.get("uncategorized", 0) > 0.50:
        return _SURFACE_ACTIONS["uncategorized"]
    return "balanced surface, all-channel approach"
