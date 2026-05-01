"""Perplexity engine using OpenAI-compatible API (sonar model includes web search natively)."""
from __future__ import annotations

import time
from urllib.parse import urlparse

PERPLEXITY_BASE_URL = "https://api.perplexity.ai"


def _domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _extract_citations(response, content_text: str) -> list[dict]:
    """
    Perplexity returns citations as:
    1. response.citations — list of URL strings (primary source)
    2. Markdown links in the content text (fallback)
    """
    citations: list[dict] = []
    seen: set[str] = set()

    # Primary: response.citations field (list of URL strings)
    raw_citations = getattr(response, "citations", None) or []
    for url in raw_citations:
        if isinstance(url, str) and url not in seen:
            seen.add(url)
            citations.append({"url": url, "title": "", "domain": _domain_of(url)})

    # Fallback: parse URLs from markdown content
    if not citations and content_text:
        import re
        for url in re.findall(r"https?://[^\s\)\]\"']+", content_text):
            url = url.rstrip(".,;:")
            if url not in seen:
                seen.add(url)
                citations.append({"url": url, "title": "", "domain": _domain_of(url)})

    return citations


def _position_of(citations: list[dict], target: str) -> int | None:
    for i, c in enumerate(citations, 1):
        if target in c["domain"]:
            return i
    return None


def run_query(
    query: str,
    target_domain: str,
    model: str,
    api_key: str,
    runs: int,
    **_kwargs,
) -> dict:
    """Run query through Perplexity's sonar model. Missing key → raises RuntimeError."""
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai SDK not installed. Run: pip install openai")

    client = OpenAI(api_key=api_key, base_url=PERPLEXITY_BASE_URL)
    prompt = (
        "I'm researching this as a buyer. Give me a concise answer and cite the "
        f"sources you used.\n\nQuery: {query}"
    )

    raw_runs: list[dict] = []
    positions: list[int] = []
    union: list[dict] = []
    seen_urls: set[str] = set()

    for r in range(runs):
        t0 = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            content_text = response.choices[0].message.content or ""
            cites = _extract_citations(response, content_text)
        except Exception as e:
            print(f"    [perplexity] run {r+1}/{runs} FAILED: {e}", file=__import__('sys').stderr)
            continue

        elapsed = int((time.perf_counter() - t0) * 1000)
        pos = _position_of(cites, target_domain)
        if pos:
            positions.append(pos)
        for c in cites:
            if c["url"] not in seen_urls:
                seen_urls.add(c["url"])
                union.append(c)
        status = f"cited at #{pos}" if pos else f"not cited ({len(cites)} URLs)"
        print(f"    [perplexity] run {r+1}/{runs}: {status} ({elapsed}ms)", file=__import__('sys').stderr)
        raw_runs.append({"citations": cites})

    import statistics
    cited = len(positions) > 0
    rate = round(len(positions) / runs, 2) if runs else 0.0
    return {
        "cited": cited,
        "citation_rate": rate,
        "citations_union": union,
        "runs": len(raw_runs),
        "raw_runs": raw_runs,
        "position_mode": statistics.mode(positions) if positions else None,
        "position_min": min(positions) if positions else None,
        "position_max": max(positions) if positions else None,
    }
