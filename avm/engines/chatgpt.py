"""ChatGPT engine using OpenAI Responses API with web_search_preview tool."""
from __future__ import annotations

import time
from urllib.parse import urlparse


def _domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _extract_citations(response) -> list[dict]:
    """Parse citations from OpenAI Responses API output."""
    citations: list[dict] = []
    seen: set[str] = set()

    output = getattr(response, "output", None) or []
    for item in output:
        item_type = getattr(item, "type", None)
        if item_type == "message":
            for part in getattr(item, "content", None) or []:
                part_type = getattr(part, "type", None)
                # output_text parts carry URL annotations
                text = getattr(part, "text", None) or ""
                annotations = getattr(part, "annotations", None) or []
                for ann in annotations:
                    ann_type = getattr(ann, "type", None)
                    if ann_type == "url_citation":
                        url = getattr(ann, "url", None) or ""
                        title = getattr(ann, "title", None) or ""
                        if url and url not in seen:
                            seen.add(url)
                            citations.append({"url": url, "title": title, "domain": _domain_of(url)})
        # web_search_call results may also contain source URLs
        elif item_type == "web_search_call":
            pass  # results come back via annotations on the message

    # Fallback: if no annotations, parse markdown links from output text
    if not citations:
        import re
        full_text = ""
        for item in output:
            if getattr(item, "type", None) == "message":
                for part in getattr(item, "content", None) or []:
                    full_text += getattr(part, "text", None) or ""
        for url in re.findall(r"https?://[^\s\)\]\"']+", full_text):
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
    """Run query through ChatGPT with web search. Missing key → raises RuntimeError."""
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai SDK not installed. Run: pip install openai")

    client = OpenAI(api_key=api_key)
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
            response = client.responses.create(
                model=model,
                tools=[{"type": "web_search_preview"}],
                input=prompt,
            )
            cites = _extract_citations(response)
        except Exception as e:
            print(f"    [chatgpt] run {r+1}/{runs} FAILED: {e}")
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
        print(f"    [chatgpt] run {r+1}/{runs}: {status} ({elapsed}ms)")
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
