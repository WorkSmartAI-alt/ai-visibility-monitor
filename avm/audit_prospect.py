"""AI Visibility Readiness audit orchestrator.

Scores any public domain 0-100 across six categories and produces a
single-page consultant report.

Usage:
    avm audit-prospect https://example.com
    avm audit-prospect https://example.com --json
"""
from __future__ import annotations

import json
import random
import re
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

AUDIT_UA = "AIVisibilityMonitor/1.0 (+https://github.com/WorkSmartAI-alt/ai-visibility-monitor)"
# Use a known bot UA for page-content fetches so pre-render layers serve full HTML
CONTENT_UA = "Mozilla/5.0 (compatible; GPTBot/1.0; +https://openai.com/gptbot)"
_LOC_RE = re.compile(r"<loc>\s*([^<]+)\s*</loc>", re.IGNORECASE)
_SITEMAP_INDEX_RE = re.compile(r"<sitemapindex", re.IGNORECASE)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _fetch(url: str, ua: str | None = None, timeout: int = 5) -> dict:
    """Fetch a URL and return a structured result including response headers.

    Never raises. Always returns a dict with status, ok, body, headers,
    size, error, latency_ms, and final_url.
    """
    result: dict = {
        "url": url,
        "final_url": url,
        "status": None,
        "ok": False,
        "body": "",
        "headers": {},
        "size": 0,
        "error": None,
        "latency_ms": None,
    }
    start = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": ua or AUDIT_UA})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read(2_000_000)
            result["status"] = resp.status
            result["ok"] = 200 <= resp.status < 300
            result["body"] = body.decode("utf-8", errors="replace")
            result["size"] = len(body)
            result["final_url"] = resp.geturl()
            result["headers"] = dict(resp.headers)
    except urllib.error.HTTPError as e:
        result["status"] = e.code
        result["error"] = f"HTTPError {e.code}"
    except urllib.error.URLError as e:
        result["error"] = f"URLError {e.reason}"
    except (TimeoutError, ssl.SSLError, ConnectionError, OSError) as e:
        result["error"] = f"{type(e).__name__}: {e}"
    except Exception as e:  # noqa: BLE001
        result["error"] = f"Unexpected {type(e).__name__}: {e}"
    result["latency_ms"] = int((time.perf_counter() - start) * 1000)
    return result


def _fetch_head(url: str, ua: str | None = None, timeout: int = 5) -> dict:
    """HEAD request for reachability checks (og:image etc.)."""
    result: dict = {
        "url": url, "status": None, "ok": False,
        "body": "", "headers": {}, "size": 0,
        "error": None, "latency_ms": None, "final_url": url,
    }
    start = time.perf_counter()
    try:
        req = urllib.request.Request(
            url, method="HEAD", headers={"User-Agent": ua or AUDIT_UA}
        )
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            result["status"] = resp.status
            result["ok"] = 200 <= resp.status < 300
            result["headers"] = dict(resp.headers)
            result["final_url"] = resp.geturl()
    except urllib.error.HTTPError as e:
        result["status"] = e.code
        result["error"] = f"HTTPError {e.code}"
    except Exception as e:  # noqa: BLE001
        result["error"] = f"{type(e).__name__}: {e}"
    result["latency_ms"] = int((time.perf_counter() - start) * 1000)
    return result


def _fetch_for_module(url: str, ua: str | None) -> dict:
    """Wrapper for module fetch_fn signature (url, ua)."""
    if ua is None:
        return _fetch_head(url)
    return _fetch(url, ua=ua)


# ---------------------------------------------------------------------------
# Sitemap helpers
# ---------------------------------------------------------------------------

def _extract_urls_from_sitemap(body: str, base_url: str, limit: int = 50) -> list[str]:
    """Return page URLs from a sitemap or sitemap index body."""
    if _SITEMAP_INDEX_RE.search(body):
        # Sitemap index: follow first 3 child sitemaps
        child_locs = _LOC_RE.findall(body)[:3]
        urls: list[str] = []
        for child in child_locs:
            child_url = child if child.startswith("http") else urljoin(base_url, child)
            r = _fetch(child_url)
            if r["ok"]:
                urls.extend(_LOC_RE.findall(r["body"]))
            if len(urls) >= limit:
                break
        return urls[:limit]
    return _LOC_RE.findall(body)[:limit]


def _sample_urls(all_urls: list[str], home_url: str, n: int = 10) -> list[str]:
    """Return up to n URLs, always including home, random-sampled from the rest."""
    other = [u for u in all_urls if u.rstrip("/") != home_url.rstrip("/")]
    if len(other) <= n - 1:
        selected = other
    else:
        selected = random.sample(other, n - 1)
    return [home_url] + selected


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _letter_grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _rank_fixes(categories: dict) -> list[dict]:
    """Collect all fixes from all categories, sort by impact-per-effort, return top 3."""
    all_fixes: list[dict] = []
    for cat_result in categories.values():
        all_fixes.extend(cat_result.get("fixes", []))

    # Sort by points_gained / effort_minutes (descending), break ties by points_gained
    def sort_key(f: dict) -> tuple[float, float]:
        pts = f.get("points_gained", 0.0)
        effort = max(f.get("effort_minutes", 1), 1)
        return (-round(pts / effort, 4), -pts)

    seen: set[str] = set()
    deduped: list[dict] = []
    for fix in sorted(all_fixes, key=sort_key):
        key = fix.get("key", fix["description"])
        if key not in seen:
            seen.add(key)
            deduped.append(fix)

    return deduped[:3]


def _effort_label(minutes: int) -> str:
    if minutes < 60:
        return f"~{minutes}m"
    hours = minutes // 60
    return f"~{hours}h"


# ---------------------------------------------------------------------------
# Main audit entry point
# ---------------------------------------------------------------------------

def run_audit(domain_url: str, timeout: int = 5) -> dict:
    """Run a full AI Visibility Readiness audit against domain_url.

    Args:
        domain_url: Full URL like https://example.com or bare domain.
        timeout: Per-request HTTP timeout in seconds.

    Returns a structured dict with score, grade, category results, and top fixes.
    """
    from avm.audit_modules import (
        crawler_access,
        discovery_files,
        meta_html_quality,
        og_social,
        render_performance,
        schema_markup,
    )
    from avm.audit_modules._html import parse_page

    if not domain_url.startswith("http"):
        domain_url = "https://" + domain_url
    parsed = urlparse(domain_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    domain = parsed.netloc

    start_time = time.perf_counter()

    # ------------------------------------------------------------------
    # Fetch infrastructure files
    # ------------------------------------------------------------------
    robots_r = _fetch(base_url + "/robots.txt", timeout=timeout)
    robots_body = robots_r["body"] if robots_r["ok"] else None

    llms_r = _fetch(base_url + "/llms.txt", timeout=timeout)
    llms_status = llms_r["status"] if llms_r["ok"] else llms_r["status"]

    # Find sitemap: try robots.txt declarations first, then /sitemap.xml
    sitemap_candidates: list[str] = []
    if robots_body:
        sitemap_candidates = [
            line.partition(":")[2].strip()
            for line in robots_body.splitlines()
            if line.lower().startswith("sitemap:")
        ]
    sitemap_candidates.append(base_url + "/sitemap.xml")
    sitemap_candidates = list(dict.fromkeys(sitemap_candidates))  # dedup, preserve order

    sitemap_r: dict = {"ok": False, "status": None, "body": "", "headers": {}}
    for cand in sitemap_candidates:
        if not cand.startswith("http"):
            cand = urljoin(base_url, cand)
        r = _fetch(cand, timeout=timeout)
        if r["ok"] and ("<urlset" in r["body"].lower() or "<sitemapindex" in r["body"].lower()):
            sitemap_r = r
            break

    sitemap_body = sitemap_r["body"]
    sitemap_last_modified = sitemap_r.get("headers", {}).get("Last-Modified") or sitemap_r.get("headers", {}).get("last-modified")
    sitemap_status = sitemap_r.get("status")

    # ------------------------------------------------------------------
    # Build URL sample
    # ------------------------------------------------------------------
    all_sitemap_urls = _extract_urls_from_sitemap(sitemap_body, base_url) if sitemap_body else []
    sampled_10 = _sample_urls(all_sitemap_urls, base_url + "/", n=10) if all_sitemap_urls else [base_url + "/"]
    sampled_3 = sampled_10[:3]

    pages_count = len(sampled_10)

    # ------------------------------------------------------------------
    # Fetch and parse sampled pages (for schema, meta, OG)
    # Use a bot UA so pre-render layers serve fully rendered HTML
    # ------------------------------------------------------------------
    page_data_list = []
    for url in sampled_10:
        r = _fetch(url, ua=CONTENT_UA, timeout=timeout)
        if r["ok"]:
            page_data_list.append(parse_page(r["final_url"] or url, r["body"]))

    page_data_3 = page_data_list[:3]

    # ------------------------------------------------------------------
    # Run all 6 category audits
    # ------------------------------------------------------------------
    cat_crawler = crawler_access.audit(robots_body)

    cat_discovery = discovery_files.audit(
        llms_status=llms_status,
        sitemap_status=sitemap_status,
        sitemap_body=sitemap_body,
        sitemap_last_modified=sitemap_last_modified,
        robots_body=robots_body,
    )

    cat_schema = schema_markup.audit(page_data_list)

    cat_render = render_performance.audit(sampled_3, _fetch_for_module)

    cat_meta = meta_html_quality.audit(page_data_3)

    cat_og = og_social.audit(page_data_3, _fetch_for_module)

    categories = {
        "crawler_accessibility": cat_crawler,
        "discovery_files": cat_discovery,
        "schema_markup": cat_schema,
        "render_performance": cat_render,
        "meta_html_quality": cat_meta,
        "og_social": cat_og,
    }

    # ------------------------------------------------------------------
    # Normalize schema max_points to 20 for totaling purposes
    # ------------------------------------------------------------------
    raw_total = sum(c["points"] for c in categories.values())
    declared_max = sum(c["max_points"] for c in categories.values())

    # Scale to 100: if schema had no blog URLs its max is 15 not 20,
    # making declared_max 95 instead of 100. Normalize to 100.
    score = int(round(raw_total / declared_max * 100)) if declared_max else 0
    score = max(0, min(100, score))
    grade = _letter_grade(score)

    top_fixes = _rank_fixes(categories)
    for fix in top_fixes:
        fix["effort_label"] = _effort_label(fix.get("effort_minutes", 60))

    elapsed = round(time.perf_counter() - start_time, 1)

    return {
        "domain": domain,
        "audited_url": base_url,
        "run_date_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "elapsed_seconds": elapsed,
        "score": score,
        "grade": grade,
        "pages_sampled": pages_count,
        "categories": categories,
        "top_fixes": top_fixes,
    }
