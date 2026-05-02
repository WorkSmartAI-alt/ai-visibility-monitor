"""Adjacent query discovery for --expand mode."""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter

from avm.surfaces import surface_distribution, get_parent_surface


def _infer_icp(base_queries: list[str]) -> str:
    """
    Extract ICP signals from the base queries for use in the expansion prompt.
    Returns a 1-2 sentence description of what's in-scope vs out-of-scope.
    """
    text = " ".join(base_queries).lower()

    segments: list[str] = []
    if any(w in text for w in ["family office", "wealth", "asset management", "investment"]):
        segments.append("wealth management / family office")
    if any(w in text for w in ["construction", "building", "contractor", "capataz"]):
        segments.append("construction")
    if any(w in text for w in ["legal", "law firm", "attorney", "counsel"]):
        segments.append("legal")
    if any(w in text for w in ["mid-market", "enterprise", "b2b", "company", "companies"]):
        segments.append("mid-market B2B")
    if any(w in text for w in ["fractional", "consulting", "consultant", "advisor"]):
        segments.append("consulting / advisory services")
    if any(w in text for w in ["ai", "machine learning", "llm", "claude", "gpt", "visibility"]):
        segments.append("AI tools / AI adoption")

    if not segments:
        return ""

    in_scope = ", ".join(segments)
    return (
        f"The buyer ICP inferred from these queries is: {in_scope}. "
        f"Stick to adjacent queries a REAL BUYER in this context would type. "
        f"Do NOT generate queries for academic researchers, students, job seekers, "
        f"unrelated industries, or consumer use cases."
    )


def generate_adjacent_queries(
    base_queries: list[str],
    target_count: int = 15,
    model: str = "claude-haiku-4-5-20251001",
    api_key: str | None = None,
) -> list[str]:
    """
    Use Claude to generate adjacent queries by varying specificity, intent, and vocabulary.
    ICP-constrained: infers the buyer profile from base queries and filters out-of-scope queries.
    Returns list of up to target_count new queries (no duplicates with base queries).
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic SDK not installed. Run: pip install anthropic")

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("No ANTHROPIC_API_KEY set — needed for adjacent query generation.")

    icp_constraint = _infer_icp(base_queries)
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
    )

    if icp_constraint:
        prompt += (
            f"- ICP CONSTRAINT: {icp_constraint}\n"
            "- OUT-OF-SCOPE examples (do NOT generate): 'ai for academic research', "
            "'citation tools for students', 'ai visibility for researchers'\n"
            "- IN-SCOPE examples: queries a mid-market business operator or executive would ask\n"
        )

    prompt += "- Return as JSON array of strings, no commentary"

    client = anthropic.Anthropic(api_key=key)
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()

    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        queries = json.loads(raw)
    except json.JSONDecodeError:
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
    1.0 = all soft surfaces (community, blogs)
    """
    soft_parents = {"community", "blog", "other"}
    hard_parents = {"press", "official"}

    if not citations_union:
        return 0.5

    dist = surface_distribution(citations_union)
    total = sum(dist.values())
    if total == 0:
        return 0.5

    soft_count = sum(
        cnt for leaf, cnt in dist.items()
        if get_parent_surface(leaf) in soft_parents
    )
    hard_count = sum(
        cnt for leaf, cnt in dist.items()
        if get_parent_surface(leaf) in hard_parents
    )
    score = (soft_count - hard_count) / total
    return round((score + 1) / 2, 3)  # map [-1,1] → [0,1]


def _citation_concentration(citations_union: list[dict]) -> float:
    """
    0.0 = even spread across many domains
    1.0 = single domain dominates
    """
    if not citations_union:
        return 0.0
    domain_counts: Counter = Counter(
        c.get("domain", "") for c in citations_union if c.get("domain")
    )
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
    Compute winnability_score for each expanded query result.

    Score components (weighted additive so spread is guaranteed):
      - 35%: inverse concentration (spread of citing domains)
      - 25%: surface softness (community/blog vs press/official)
      - 25%: inverse density (fewer total unique citing domains = less competition)
      - 15%: partial visibility (are you already anywhere near this space)

    Returns list sorted descending by winnability_score.
    """
    scored: list[dict] = []
    for q in expanded_results:
        citations = q.get("citations_union", [])

        concentration = _citation_concentration(citations)
        softness = _surface_softness(citations)

        unique_domains = len({c.get("domain", "") for c in citations if c.get("domain")})
        # 8+ unique citing domains = max competition (score 0); 0 = uncrowded (score 1)
        density_score = 1.0 - min(unique_domains / 8.0, 1.0)

        any_engine_cited = q.get("cited", False)
        domain_in_citations = any(
            target_domain in (c.get("domain") or "") for c in citations
        )
        if any_engine_cited:
            partial_vis = 1.0
        elif domain_in_citations:
            partial_vis = 0.4
        else:
            partial_vis = 0.0

        score = round(
            0.35 * (1 - concentration)
            + 0.25 * softness
            + 0.25 * density_score
            + 0.15 * partial_vis,
            3,
        )

        # ── Specific rationale ───────────────────────────────────────────────
        parts: list[str] = []

        # Citation density
        if unique_domains == 0:
            parts.append("no dominant winner yet (uncrowded query)")
        elif unique_domains <= 3:
            top_domain = Counter(
                c.get("domain", "") for c in citations if c.get("domain")
            ).most_common(1)
            if top_domain:
                parts.append(f"low competition ({unique_domains} citing domains, top: {top_domain[0][0]})")
        else:
            top_domain = Counter(
                c.get("domain", "") for c in citations if c.get("domain")
            ).most_common(1)
            if top_domain:
                parts.append(f"{unique_domains} domains cited ({top_domain[0][0]} leads)")

        # Surface mix
        from avm.surfaces import surface_distribution, parent_distribution
        dist = surface_distribution(citations)
        pdist = parent_distribution(dist)
        total_cites = sum(dist.values())
        if total_cites > 0:
            top_parent = max(pdist, key=pdist.get) if pdist else None
            if top_parent:
                pct = int(pdist[top_parent] / total_cites * 100)
                if pct >= 40:
                    parts.append(f"{pct}% {top_parent} surfaces")

        # Visibility
        if any_engine_cited:
            cited_by = q.get("cited_by", [])
            from avm.engines import ENGINE_REGISTRY
            labels = [ENGINE_REGISTRY.get(e, {}).get("label", e) for e in cited_by]
            parts.append(f"already cited by {', '.join(labels)}")
        elif domain_in_citations:
            parts.append("domain appears in adjacent citations")

        rationale = "; ".join(parts) if parts else "moderate opportunity"
        scored.append({
            "query": q["query"],
            "winnability_score": score,
            "rationale": rationale,
        })

    scored.sort(key=lambda x: x["winnability_score"], reverse=True)
    return scored
