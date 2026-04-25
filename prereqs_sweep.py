#!/usr/bin/env python3
"""
Prerequisites Sweep · AI Visibility Monitor

For each site in sites.json, checks three things:
  1. robots.txt:   does it exist, and does it allow the AI bots we care about?
  2. llms.txt:     does the emerging AI visibility file exist?
  3. sitemap.xml:  does it return XML, how many URLs are discoverable?

Writes two artifacts per run:
  - JSON  : machine-readable, feeds any dashboard layer
  - MD    : human-readable, drop into a monthly executive brief

No credentials required. Pure stdlib HTTP. Run it cold from any machine.

Usage:
  python3 prereqs_sweep.py

Setup:
  cp sites.json.example sites.json
  # edit sites.json with your domains

Part of the AI Visibility Monitor toolkit. Built by Ignacio Lopez (Work-Smart.ai).
MIT licensed. https://github.com/WorkSmartAI-alt/ai-visibility-monitor
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import urllib.request
import urllib.error
import ssl


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

# Bots that matter for AI search visibility, ordered by importance in 2026
AI_BOTS = [
    "GPTBot",              # OpenAI / ChatGPT
    "ClaudeBot",           # Anthropic / Claude
    "PerplexityBot",       # Perplexity
    "Google-Extended",     # Google AI Overviews / Gemini training
    "Applebot-Extended",   # Apple Intelligence
    "CCBot",               # Common Crawl (feeds many models)
    "Bytespider",          # ByteDance / Doubao
    "Meta-ExternalAgent",  # Meta AI
]

TIMEOUT = 10  # seconds
USER_AGENT = "AIVisibilityMonitor/1.0 (+https://github.com/WorkSmartAI-alt/ai-visibility-monitor)"


# ---------------------------------------------------------------------------
# Site config loading
# ---------------------------------------------------------------------------

def load_sites(here: Path) -> list[dict]:
    config_path = here / "sites.json"
    example_path = here / "sites.json.example"
    if not config_path.exists():
        print("ERROR: sites.json not found.", file=sys.stderr)
        if example_path.exists():
            print(f"Copy {example_path.name} to sites.json and edit:", file=sys.stderr)
            print(f"  cp {example_path} {config_path}", file=sys.stderr)
        sys.exit(2)
    try:
        sites = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: sites.json is not valid JSON: {e}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(sites, list) or not sites:
        print("ERROR: sites.json must be a non-empty array of {name, url, owner} objects.", file=sys.stderr)
        sys.exit(2)
    for i, s in enumerate(sites):
        if not all(k in s for k in ("name", "url")):
            print(f"ERROR: sites.json entry {i} missing name or url.", file=sys.stderr)
            sys.exit(2)
        s.setdefault("owner", "unspecified")
    return sites


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def fetch(url: str, timeout: int = TIMEOUT) -> dict:
    """Fetch a URL and return structured result. Never raises."""
    result = {
        "url": url,
        "status": None,
        "ok": False,
        "body": "",
        "size": 0,
        "error": None,
        "latency_ms": None,
    }
    start = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read(2_000_000)  # cap at 2MB
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


# ---------------------------------------------------------------------------
# robots.txt parsing
# ---------------------------------------------------------------------------

def parse_robots(body: str) -> dict:
    """
    Return per-bot verdicts: 'allow', 'disallow-all', 'disallow-some', 'unlisted'.
    Also captures sitemap URLs declared inside robots.txt.
    """
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
        key = key.strip().lower()
        value = value.strip()

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

    def verdict_for(agent_rules: list[str]) -> str:
        if not agent_rules:
            return "allow"
        disallows = [r for r in agent_rules if not r.startswith("__allow__:")]
        if not disallows:
            return "allow"
        if any(r == "/" for r in disallows):
            return "disallow-all"
        if all(r == "" for r in disallows):
            return "allow"
        return "disallow-some"

    wildcard_rules = groups.get("*", [])
    wildcard_verdict = verdict_for(wildcard_rules)

    for bot in AI_BOTS:
        matched = next((k for k in groups if k.lower() == bot.lower()), None)
        if matched is not None:
            verdicts[bot] = verdict_for(groups[matched])
        else:
            verdicts[bot] = wildcard_verdict

    return {"verdicts": verdicts, "sitemaps_declared": sitemaps}


# ---------------------------------------------------------------------------
# sitemap.xml parsing
# ---------------------------------------------------------------------------

URL_COUNT_RE = re.compile(r"<loc>\s*([^<]+)\s*</loc>", re.IGNORECASE)
SITEMAP_INDEX_RE = re.compile(r"<sitemapindex", re.IGNORECASE)


def inspect_sitemap(root_url: str, body: str) -> dict:
    is_index = bool(SITEMAP_INDEX_RE.search(body))
    locs = URL_COUNT_RE.findall(body)

    if is_index:
        child_urls = locs[:3]
        total = 0
        fetched = 0
        for child in child_urls:
            child_url = child if child.startswith("http") else urljoin(root_url, child)
            r = fetch(child_url)
            if r["ok"]:
                total += len(URL_COUNT_RE.findall(r["body"]))
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


# ---------------------------------------------------------------------------
# Per-site sweep
# ---------------------------------------------------------------------------

def sweep_site(site: dict) -> dict:
    base = site["url"].rstrip("/")
    out = {
        "name": site["name"],
        "url": site["url"],
        "owner": site["owner"],
        "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "robots": None,
        "llms": None,
        "sitemap": None,
        "reachable": None,
    }

    root = fetch(base + "/")
    out["reachable"] = {"status": root["status"], "ok": root["ok"], "error": root["error"], "latency_ms": root["latency_ms"]}

    r = fetch(base + "/robots.txt")
    robots_parsed = parse_robots(r["body"]) if r["ok"] else {"verdicts": {b: "unknown" for b in AI_BOTS}, "sitemaps_declared": []}
    out["robots"] = {
        "url": base + "/robots.txt",
        "status": r["status"],
        "exists": r["ok"],
        "size": r["size"],
        "error": r["error"],
        "verdicts": robots_parsed["verdicts"],
        "sitemaps_declared": robots_parsed["sitemaps_declared"],
    }

    l = fetch(base + "/llms.txt")
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
        s = fetch(cand)
        if s["ok"] and ("<urlset" in s["body"].lower() or "<sitemapindex" in s["body"].lower()):
            chosen = (cand, s)
            break

    if chosen is None:
        out["sitemap"] = {"url": candidate_sitemaps[0] if candidate_sitemaps else None, "exists": False, "error": "no reachable sitemap"}
    else:
        cand, s = chosen
        shape = inspect_sitemap(cand, s["body"])
        out["sitemap"] = {
            "url": cand,
            "status": s["status"],
            "exists": True,
            "size": s["size"],
            **shape,
        }

    return out


# ---------------------------------------------------------------------------
# Score + Markdown output
# ---------------------------------------------------------------------------

def score_site(site_result: dict) -> dict:
    score = 0
    max_score = 0

    max_score += 10
    if site_result["robots"]["exists"]:
        score += 10

    critical = ["GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "Applebot-Extended"]
    for bot in critical:
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
        score = score_site(r)
        reach = "yes" if r["reachable"]["ok"] else "no"
        robots = "yes" if r["robots"]["exists"] else "no"
        llms = "yes" if r["llms"]["exists"] else "no"
        sm_urls = r["sitemap"].get("urls_in_sampled_children", 0) if r["sitemap"].get("exists") else 0
        sitemap = f"yes ({sm_urls} URLs)" if r["sitemap"].get("exists") else "no"
        v = r["robots"]["verdicts"]
        lines.append(
            f"| {r['name']} | {reach} | {score['score']}/100 | {robots} | {llms} | {sitemap} | "
            f"{v.get('GPTBot','?')} | {v.get('ClaudeBot','?')} | {v.get('PerplexityBot','?')} |"
        )

    lines.append("")
    lines.append("## Fixes needed")
    lines.append("")
    any_fix = False
    for r in results:
        issues = []
        if not r["reachable"]["ok"]:
            issues.append(f"site unreachable from this environment ({r['reachable']['error']})")
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
            for i in issues:
                lines.append(f"  - {i}")
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    here = Path(__file__).resolve().parent
    data_dir = here / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    sites = load_sites(here)

    results = []
    for site in sites:
        print(f"[sweep] {site['name']} ...", flush=True)
        res = sweep_site(site)
        res["score"] = score_site(res)
        results.append(res)

    bundle = {
        "run_date_utc": run_date,
        "generator": "prereqs_sweep.py",
        "version": "1.0",
        "sites": results,
    }

    json_path = data_dir / f"prereqs-{run_date}.json"
    json_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    md_path = data_dir / f"prereqs-{run_date}.md"
    md_path.write_text(to_markdown(results, run_date), encoding="utf-8")

    (data_dir / "prereqs-latest.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    (data_dir / "prereqs-latest.md").write_text(to_markdown(results, run_date), encoding="utf-8")

    print(f"\n[done] wrote {json_path}")
    print(f"[done] wrote {md_path}")
    print(f"[done] wrote prereqs-latest.json and prereqs-latest.md")


if __name__ == "__main__":
    sys.exit(main())
