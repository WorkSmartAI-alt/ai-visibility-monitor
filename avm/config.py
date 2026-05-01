from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


def load_queries(path: Path) -> list[str]:
    """Read queries from queries.md, skipping headers, blockquotes, and subsections."""
    queries: list[str] = []
    stop = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.match(r"^#{2,}\s", line):
            stop = True
            continue
        if stop:
            continue
        if line.startswith("#") or line.startswith(">") or line.startswith("```"):
            continue
        line = re.sub(r"^[-*+]\s+", "", line)
        line = re.sub(r"^\d+[.)]\s+", "", line)
        if (line.startswith('"') and line.endswith('"')) or (line.startswith("'") and line.endswith("'")):
            line = line[1:-1]
        if line:
            queries.append(line)
    return queries[:10]


def _domain_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def load_sites(path: Path) -> dict:
    """
    Read sites.json (array of {name, url, owner} objects).
    Returns {"primary_domain": str, "competitors": [str], "sites": [dict]}.
    """
    if not path.exists():
        print(f"ERROR: {path} not found.", file=sys.stderr)
        example = path.parent / "sites.json.example"
        if example.exists():
            print("  cp sites.json.example sites.json", file=sys.stderr)
        sys.exit(2)
    try:
        sites = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: {path} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(sites, list) or not sites:
        print(f"ERROR: {path} must be a non-empty array.", file=sys.stderr)
        sys.exit(2)
    self_site = next((s for s in sites if s.get("owner") == "self"), sites[0])
    primary = _domain_from_url(self_site["url"])
    others = [_domain_from_url(s["url"]) for s in sites if s is not self_site]
    return {"primary_domain": primary, "competitors": others, "sites": sites}
