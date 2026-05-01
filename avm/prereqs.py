from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

AI_BOTS = [
    "GPTBot",
    "ClaudeBot",
    "PerplexityBot",
    "Google-Extended",
    "Applebot-Extended",
    "CCBot",
    "Bytespider",
    "Meta-ExternalAgent",
]

USER_AGENT = "AIVisibilityMonitor/1.0 (+https://github.com/WorkSmartAI-alt/ai-visibility-monitor)"

_URL_COUNT_RE = re.compile(r"<loc>\s*([^<]+)\s*</loc>", re.IGNORECASE)
_SITEMAP_INDEX_RE = re.compile(r"<sitemapindex", re.IGNORECASE)


def _fetch(url: str, timeout: int = 10) -> dict:
    """Fetch a URL and return a structured result. Never raises."""
    result = {"url": url, "status": None, "ok": False, "body": "", "size": 0, "error": None, "latency_ms": None}
    start = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read(2_000_000)
            result["status"] = resp.status
            result["ok"] = 200 <= resp.status < 300
            result["body"] = body.decode("utf-8", errors="replace")
            result["size"] = len(body)
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


def _parse_robots(body: str) -> dict:
    verdicts = {bot: "unlisted" for bot in AI_BOTS}
    sitemaps: list[str] = []
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
        elif key == "disallow" and current_agents:
            for agent in current_agents:
                groups.setdefault(agent, []).append(value)
        elif key == "allow" and current_agents:
            for agent in current_agents:
                groups.setdefault(agent, []).append(f"__allow__:{value}")
        elif key == "sitemap":
            sitemaps.append(value)

    def verdict_for(rules: list[str]) -> str:
        if not rules:
            return "allow"
        disallows = [r for r in rules if not r.startswith("__allow__:")]
        if not disallows:
            return "allow"
        if any(r == "/" for r in disallows):
            return "disallow-all"
        if all(r == "" for r in disallows):
            return "allow"
        return "disallow-some"

    wildcard_verdict = verdict_for(groups.get("*", []))
    for bot in AI_BOTS:
        matched = next((k for k in groups if k.lower() == bot.lower()), None)
        verdicts[bot] = verdict_for(groups[matched]) if matched else wildcard_verdict

    return {"verdicts": verdicts, "sitemaps_declared": sitemaps}


def _inspect_sitemap(root_url: str, body: str, timeout: int = 10) -> dict:
    is_index = bool(_SITEMAP_INDEX_RE.search(body))
    locs = _URL_COUNT_RE.findall(body)
    if is_index:
        child_urls = locs[:3]
        total = 0
        fetched = 0
        for child in child_urls:
            child_url = child if child.startswith("http") else urljoin(root_url, child)
            r = _fetch(child_url, timeout=timeout)
            if r["ok"]:
                total += len(_URL_COUNT_RE.findall(r["body"]))
                fetched += 1
        return {
            "is_sitemap_index": True,
            "child_sitemaps_declared": len(locs),
            "child_sitemaps_sampled": fetched,
            "urls_in_sampled_children": total,
        }
    return {
        "is_sitemap_index": False,
        "child_sitemaps_declared": 0,
        "child_sitemaps_sampled": 0,
        "urls_in_sampled_children": len(locs),
    }


def sweep_site(site: dict, timeout: int = 10) -> dict:
    """Sweep a single site dict {name, url, owner} and return the audit result."""
    base = site["url"].rstrip("/")
    out = {
        "name": site["name"],
        "url": site["url"],
        "owner": site.get("owner", "unspecified"),
        "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "robots": None,
        "llms": None,
        "sitemap": None,
        "reachable": None,
    }

    root = _fetch(base + "/", timeout=timeout)
    out["reachable"] = {
        "status": root["status"], "ok": root["ok"],
        "error": root["error"], "latency_ms": root["latency_ms"],
    }

    r = _fetch(base + "/robots.txt", timeout=timeout)
    robots_parsed = (
        _parse_robots(r["body"]) if r["ok"]
        else {"verdicts": {b: "unknown" for b in AI_BOTS}, "sitemaps_declared": []}
    )
    out["robots"] = {
        "url": base + "/robots.txt",
        "status": r["status"],
        "exists": r["ok"],
        "size": r["size"],
        "error": r["error"],
        "verdicts": robots_parsed["verdicts"],
        "sitemaps_declared": robots_parsed["sitemaps_declared"],
    }

    l = _fetch(base + "/llms.txt", timeout=timeout)
    out["llms"] = {
        "url": base + "/llms.txt",
        "status": l["status"],
        "exists": l["ok"],
        "size": l["size"],
        "first_line": l["body"].splitlines()[0].strip() if l["ok"] and l["body"].strip() else None,
    }

    candidate_sitemaps = list(dict.fromkeys([*out["robots"]["sitemaps_declared"], base + "/sitemap.xml"]))
    chosen = None
    for cand in candidate_sitemaps:
        s = _fetch(cand, timeout=timeout)
        if s["ok"] and ("<urlset" in s["body"].lower() or "<sitemapindex" in s["body"].lower()):
            chosen = (cand, s)
            break

    if chosen is None:
        out["sitemap"] = {
            "url": candidate_sitemaps[0] if candidate_sitemaps else None,
            "exists": False,
            "error": "no reachable sitemap",
        }
    else:
        cand, s = chosen
        shape = _inspect_sitemap(cand, s["body"], timeout=timeout)
        out["sitemap"] = {"url": cand, "status": s["status"], "exists": True, "size": s["size"], **shape}

    return out


def score_site(site_result: dict) -> dict:
    score = 0
    max_score = 0
    max_score += 10
    if site_result["robots"]["exists"]:
        score += 10
    for bot in ["GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "Applebot-Extended"]:
        max_score += 5
        v = site_result["robots"]["verdicts"].get(bot, "unknown")
        if v == "allow":
            score += 5
        elif v == "disallow-some":
            score += 3
    max_score += 15
    if site_result["llms"]["exists"]:
        score += 15
    max_score += 15
    if site_result["sitemap"].get("exists"):
        score += 15
    max_score += 10
    if site_result["reachable"]["ok"]:
        score += 10
    return {"score": round(100 * score / max_score) if max_score else 0, "points": score, "max": max_score}


def to_markdown(results: list[dict], run_date: str) -> str:
    lines = [
        f"# Prerequisites Sweep · {run_date}",
        "",
        "> AI bot access, llms.txt, sitemap health across all monitored sites.",
        "",
        "## Headline",
        "",
    ]
    reachable_count = sum(1 for r in results if r["reachable"]["ok"])
    llms_count = sum(1 for r in results if r["llms"]["exists"])
    lines.append(f"- **Sites reached:** {reachable_count} of {len(results)}")
    lines.append(f"- **llms.txt present:** {llms_count} of {reachable_count} reachable")
    lines.append("")
    lines.append("## Per-site table")
    lines.append("")
    lines.append("| Site | Reachable | Score | robots.txt | llms.txt | Sitemap | GPTBot | ClaudeBot | PerplexityBot |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        s = score_site(r)
        reach = "yes" if r["reachable"]["ok"] else "no"
        robots = "yes" if r["robots"]["exists"] else "no"
        llms = "yes" if r["llms"]["exists"] else "no"
        sm_urls = r["sitemap"].get("urls_in_sampled_children", 0) if r["sitemap"].get("exists") else 0
        sitemap = f"yes ({sm_urls} URLs)" if r["sitemap"].get("exists") else "no"
        v = r["robots"]["verdicts"]
        lines.append(
            f"| {r['name']} | {reach} | {s['score']}/100 | {robots} | {llms} | {sitemap} | "
            f"{v.get('GPTBot','?')} | {v.get('ClaudeBot','?')} | {v.get('PerplexityBot','?')} |"
        )
    lines.append("")
    lines.append("## Fixes needed")
    lines.append("")
    any_fix = False
    for r in results:
        issues = []
        if not r["reachable"]["ok"]:
            issues.append(f"site unreachable ({r['reachable']['error']})")
        if not r["robots"]["exists"]:
            issues.append("robots.txt missing")
        for bot, verdict in r["robots"]["verdicts"].items():
            if verdict == "disallow-all":
                issues.append(f"{bot} blocked in robots.txt")
        if not r["llms"]["exists"]:
            issues.append("no llms.txt")
        if not r["sitemap"].get("exists"):
            issues.append("sitemap.xml not reachable")
        if issues:
            any_fix = True
            lines.append(f"**{r['name']}**")
            for issue in issues:
                lines.append(f"  - {issue}")
            lines.append("")
    if not any_fix:
        lines.append("Nothing to fix. All monitored sites pass basic prereqs.")
    lines.append("")
    lines.append("## Full bot matrix")
    lines.append("")
    header = "| Site | " + " | ".join(AI_BOTS) + " |"
    sep = "|---" * (len(AI_BOTS) + 1) + "|"
    lines.append(header)
    lines.append(sep)
    for r in results:
        v = r["robots"]["verdicts"]
        row = "| " + r["name"] + " | " + " | ".join(v.get(b, "?") for b in AI_BOTS) + " |"
        lines.append(row)
    lines.append("")
    lines.append(f"_Generated by prereqs_sweep.py at {datetime.now(timezone.utc).isoformat(timespec='seconds')}_")
    return "\n".join(lines)


def run_prereqs_sweep(domain: str, timeout: int = 10) -> dict:
    """
    Sweep a single domain for robots.txt, llms.txt, and sitemap health.

    domain: bare domain like "example.com" or full URL like "https://example.com"
    Returns the per-site audit dict.
    """
    url = domain if domain.startswith("http") else f"https://{domain}"
    site = {"name": domain, "url": url, "owner": "self"}
    return sweep_site(site, timeout=timeout)


def main_cli() -> int:
    from avm.config import load_sites
    from avm.output import write_json

    parser = argparse.ArgumentParser(description="AI Visibility Monitor - prerequisites sweep")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--timeout", type=int, default=10, help="HTTP timeout per request (seconds)")
    args = parser.parse_args()

    here = Path(__file__).resolve().parent.parent
    data_dir = Path(args.output_dir) if args.output_dir else (here / "data")
    data_dir.mkdir(parents=True, exist_ok=True)

    sites_path = here / "sites.json"
    if not sites_path.exists():
        print("ERROR: sites.json not found.", file=sys.stderr)
        example = here / "sites.json.example"
        if example.exists():
            print("  cp sites.json.example sites.json", file=sys.stderr)
        return 2

    sites_config = load_sites(sites_path)
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    results = []
    for site in sites_config["sites"]:
        print(f"[sweep] {site['name']} ...", flush=True)
        res = sweep_site(site, timeout=args.timeout)
        res["score"] = score_site(res)
        results.append(res)

    bundle = {
        "run_date_utc": run_date,
        "generator": "prereqs_sweep.py",
        "version": "1.0",
        "sites": results,
    }

    json_path = data_dir / f"prereqs-{run_date}.json"
    write_json(bundle, json_path)

    md_text = to_markdown(results, run_date)
    md_path = data_dir / f"prereqs-{run_date}.md"
    md_path.write_text(md_text, encoding="utf-8")
    (data_dir / "prereqs-latest.md").write_text(md_text, encoding="utf-8")

    print(f"\n[done] wrote {json_path}")
    print(f"[done] wrote {md_path}")
    print("[done] wrote prereqs-latest.json and prereqs-latest.md")
    return 0
