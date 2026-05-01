"""Claude engine using Anthropic SDK with web_search tool."""
from __future__ import annotations

import statistics
import time
from urllib.parse import urlparse


def _domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _run_single(client, model: str, query: str, max_searches: int) -> dict:
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}]
    prompt = (
        "I'm researching this as a buyer. Give me a concise answer and cite the "
        f"sources you used.\n\nQuery: {query}"
    )
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        tools=tools,
        messages=[{"role": "user", "content": prompt}],
    )
    citations: list[dict] = []
    seen: set[str] = set()
    for block in resp.content:
        btype = getattr(block, "type", None)
        if btype == "text":
            for c in getattr(block, "citations", None) or []:
                ctype = getattr(c, "type", None)
                if ctype in ("web_search_result_location", "url_citation"):
                    url = getattr(c, "url", None) or ""
                    if url and url not in seen:
                        seen.add(url)
                        citations.append({"url": url, "title": getattr(c, "title", "") or "", "domain": _domain_of(url)})
        elif btype == "web_search_tool_result":
            for item in getattr(block, "content", None) or []:
                url = getattr(item, "url", None) or ""
                if url and url not in seen:
                    seen.add(url)
                    citations.append({"url": url, "title": getattr(item, "title", "") or "", "domain": _domain_of(url), "from": "search_result"})
    return {"citations": citations, "stop_reason": getattr(resp, "stop_reason", None)}


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
    max_searches: int = 5,
    **_kwargs,
) -> dict:
    """
    Returns the standard engine result dict:
    {
        "cited": bool,
        "citation_rate": float,
        "citations_union": [...],
        "runs": int,
        "raw_runs": [...],
        "position_mode": int|None,
        "position_min": int|None,
        "position_max": int|None,
    }
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic SDK not installed. Run: pip install anthropic")

    client = anthropic.Anthropic(api_key=api_key)
    raw_runs: list[dict] = []
    positions: list[int] = []
    union: list[dict] = []
    seen_urls: set[str] = set()

    for r in range(runs):
        t0 = time.perf_counter()
        try:
            single = _run_single(client, model, query, max_searches)
        except Exception as e:
            print(f"    [claude] run {r+1}/{runs} FAILED: {e}", file=__import__('sys').stderr)
            continue
        elapsed = int((time.perf_counter() - t0) * 1000)
        pos = _position_of(single["citations"], target_domain)
        if pos:
            positions.append(pos)
        for c in single["citations"]:
            if c["url"] not in seen_urls:
                seen_urls.add(c["url"])
                union.append(c)
        status = f"cited at #{pos}" if pos else f"not cited ({len(single['citations'])} URLs)"
        print(f"    [claude] run {r+1}/{runs}: {status} ({elapsed}ms)", file=__import__('sys').stderr)
        raw_runs.append({"citations": single["citations"], "stop_reason": single["stop_reason"]})

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
