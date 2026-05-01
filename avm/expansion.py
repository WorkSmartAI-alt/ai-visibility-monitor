"""Adjacent query discovery for --expand mode."""
from __future__ import annotations

import json
import os
import sys

from avm.surfaces import surface_distribution


def generate_adjacent_queries(
    base_queries: list[str],
    target_count: int = 15,
    model: str = "claude-haiku-4-5-20251001",
    api_key: str | None = None,
) -> list[str]:
    """
    Use Claude to generate adjacent queries by varying specificity, intent, and vocabulary.
    Returns list of up to target_count new queries (no duplicates with base queries).
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic SDK not installed. Run: pip install anthropic")

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("No ANTHROPIC_API_KEY set — needed for adjacent query generation.")

    base_list = "\n".join(f"- {q}" for q in base_queries)
    prompt = (
        f"You are a marketing analyst expanding a buyer-query list for AI search visibility analysis.\n\n"
        f"Given these {len(base_queries)} base queries:\n{base_list}\n\n"
        f"Generate {target_count} adjacent queries that vary across these dimensions:\n\n"
        "1. Specificity: broader (covers more), narrower (more specific), location-specific\n"
        "2. Intent: commercial (\"best X for Y\"), informational (\"what is X\"), comparison (\"X vs Y\")\n"
        "3. Vocabulary: synonyms, industry shorthand, formal vs casual phrasing\n\n"
        "Rules:\n"
        "- Each query must be a question or phrase a real buyer would type into ChatGPT or Claude\n"
        "- Each query must be different enough from the base queries to surface new citation surfaces\n"
        "- Lowercase, conversational\n"
        "- Return as JSON array of strings, no commentary"
    )

    client = anthropic.Anthropic(api_key=key)
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()

    # Extract JSON array — Claude may wrap in ```json fences
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        queries = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: extract lines that look like quoted strings
        import re
        queries = re.findall(r'"([^"]+)"', raw)

    base_set = {q.lower().strip() for q in base_queries}
    result: list[str] = []
    seen: set[str] = set()
    for q in queries:
        if not isinstance(q, str):
            continue
        q = q.strip()
        key_norm = q.lower()
        if key_norm not in base_set and key_norm not in seen:
            seen.add(key_norm)
            result.append(q)
        if len(result) >= target_count:
            break

    print(f"  [expand] generated {len(result)} adjacent queries", file=sys.stderr)
    return result


def _surface_softness(citations_union: list[dict]) -> float:
    """
    0.0 = all hard surfaces (press, official_docs, wikipedia)
    1.0 = all soft surfaces (forums, job_boards, uncategorized)
    """
    soft_cats = {"forum", "job_board", "uncategorized", "blog"}
    hard_cats = {"press", "official_docs", "wikipedia"}

    if not citations_union:
        return 0.5  # neutral when no data

    dist = surface_distribution(citations_union)
    total = sum(dist.values())
    if total == 0:
        return 0.5

    soft_count = sum(dist.get(c, 0) for c in soft_cats)
    hard_count = sum(dist.get(c, 0) for c in hard_cats)
    # Weighted: soft +1, hard -1, rest 0
    score = (soft_count - hard_count) / total
    return round((score + 1) / 2, 3)  # map [-1,1] → [0,1]


def _citation_concentration(citations_union: list[dict]) -> float:
    """
    0.0 = even spread across many domains
    1.0 = single domain dominates
    """
    if not citations_union:
        return 0.0
    from collections import Counter
    domain_counts: Counter = Counter(c.get("domain", "") for c in citations_union if c.get("domain"))
    if not domain_counts:
        return 0.0
    total = sum(domain_counts.values())
    top = domain_counts.most_common(1)[0][1]
    return round(top / total, 3)


def score_expanded_queries(
    expanded_results: list[dict],
    target_domain: str,
) -> list[dict]:
    """
    Compute winnability_score for each expanded query result and return
    list of dicts with query, winnability_score, rationale, sorted descending.
    """
    scored: list[dict] = []
    for q in expanded_results:
        citations = q.get("citations_union", [])

        concentration = _citation_concentration(citations)
        softness = _surface_softness(citations)

        # partial visibility: did the target appear at all?
        any_engine_cited = q.get("cited", False)
        partial_vis = 1.0 if any_engine_cited else (
            0.3 if any(
                target_domain in (c.get("domain") or "") for c in citations
            ) else 0.0
        )

        score = round((1 - concentration) * softness * max(partial_vis, 0.1), 3)

        # Build rationale
        parts: list[str] = []
        if concentration < 0.3:
            parts.append("low citation concentration (no dominant winner)")
        elif concentration > 0.6:
            parts.append("one domain dominates citations")
        if softness > 0.6:
            parts.append("soft surface mix (forums/blogs dominate)")
        elif softness < 0.3:
            parts.append("hard surface mix (press/official docs)")
        if any_engine_cited:
            cited_by = q.get("cited_by", [])
            from avm.engines import ENGINE_REGISTRY
            labels = [ENGINE_REGISTRY.get(e, {}).get("label", e) for e in cited_by]
            parts.append(f"already cited by {', '.join(labels)}")
        elif partial_vis == 0.3:
            parts.append("partial visibility (domain appears in citations)")

        rationale = "; ".join(parts) if parts else "moderate opportunity"
        scored.append({
            "query": q["query"],
            "winnability_score": score,
            "rationale": rationale,
        })

    scored.sort(key=lambda x: x["winnability_score"], reverse=True)
    return scored
