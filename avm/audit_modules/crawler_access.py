"""Category 1: Crawler Accessibility (30 points).

Checks whether each of the 20 canonical AI bot UAs is accessible
according to robots.txt. A UA is accessible if it has an explicit
allow rule, OR if the wildcard rule does not block it.
"""
from __future__ import annotations

AI_BOT_UAS: list[str] = [
    "GPTBot",
    "OAI-SearchBot",
    "ChatGPT-User",
    "ClaudeBot",
    "Claude-User",
    "Claude-SearchBot",
    "PerplexityBot",
    "Perplexity-User",
    "Bytespider",
    "CCBot",
    "Amazonbot",
    "Applebot",
    "Applebot-Extended",
    "meta-externalagent",
    "Meta-ExternalFetcher",
    "Google-Extended",
    "DuckAssistBot",
    "MistralAI-User",
    "Gemini-Deep-Research",
    "anthropic-ai",
]

MAX_POINTS: float = 30.0
POINTS_PER_UA: float = 1.5  # 20 UAs * 1.5 = 30


def _parse_robots(body: str) -> dict[str, list[str]]:
    """Parse robots.txt into {user-agent: [rule, ...]} groups.

    Rules are stored as "disallow:/path" or "allow:/path" strings.
    Wildcard group is keyed by "*".
    """
    groups: dict[str, list[str]] = {}
    current_agents: list[str] = []

    for raw in body.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            current_agents = []
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            current_agents = current_agents + [value] if current_agents else [value]
            groups.setdefault(value, [])
        elif key in ("disallow", "allow") and current_agents:
            for agent in current_agents:
                groups.setdefault(agent, []).append(f"{key}:{value}")

    return groups


def _is_blocked(rules: list[str]) -> bool:
    """Return True if the rule set blocks all paths (Disallow: /)."""
    for rule in rules:
        if rule.startswith("disallow:"):
            path = rule[len("disallow:"):].strip()
            if path == "/":
                return True
    return False


def _ua_accessible(ua: str, groups: dict[str, list[str]]) -> bool:
    """Return True if the UA is not fully blocked."""
    # Case-insensitive match for explicit UA group
    matched_key = next(
        (k for k in groups if k.lower() == ua.lower()),
        None,
    )
    if matched_key is not None:
        rules = groups[matched_key]
        # Explicit allow anywhere in the group means accessible
        if any(r.startswith("allow:") for r in rules):
            return True
        return not _is_blocked(rules)

    # Fall back to wildcard
    wildcard_rules = groups.get("*", [])
    return not _is_blocked(wildcard_rules)


def audit(robots_body: str | None) -> dict:
    """Score crawler accessibility from robots.txt body.

    Returns:
        {
            "points": float,
            "max_points": 30,
            "accessible_uas": [...],
            "blocked_uas": [...],
            "details": {ua: bool, ...},
        }
    """
    if not robots_body:
        # No robots.txt means no blocking rules; all bots are accessible by default.
        # Per the robots exclusion protocol, absence of robots.txt = allow all.
        return {
            "points": MAX_POINTS,
            "max_points": MAX_POINTS,
            "accessible_uas": AI_BOT_UAS[:],
            "blocked_uas": [],
            "details": {ua: True for ua in AI_BOT_UAS},
            "robots_missing": True,
        }

    groups = _parse_robots(robots_body)
    details: dict[str, bool] = {}
    for ua in AI_BOT_UAS:
        details[ua] = _ua_accessible(ua, groups)

    accessible = [ua for ua, ok in details.items() if ok]
    blocked = [ua for ua, ok in details.items() if not ok]
    points = len(accessible) * POINTS_PER_UA

    return {
        "points": round(points, 2),
        "max_points": MAX_POINTS,
        "accessible_uas": accessible,
        "blocked_uas": blocked,
        "details": details,
    }
