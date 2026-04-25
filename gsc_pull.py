#!/usr/bin/env python3
"""
GSC Pull · AI Visibility Monitor

Pulls Google Search Console performance data for any GSC property.
Rolling 28-day window ending 3 days before today (GSC has a ~2 day data lag).

Four API calls per run:
  1. by query         -> top queries (clicks desc)
  2. by page          -> top pages (clicks desc)
  3. by query+country -> country breakdown
  4. by query+device  -> device breakdown (mobile vs desktop)

Also flags striking-distance queries: position 5 to 20 with at least
N impressions (default 50 over 28 days). These are the highest-ROI
targets because Google already thinks you are relevant; you just need
a better title, a sharper answer capsule, or an FAQ block to climb
into the top 5.

Requirements:
  pip install google-api-python-client google-auth

Authentication (two supported modes):

  Mode A: Application Default Credentials (recommended for local use)
    1. Install gcloud CLI: https://cloud.google.com/sdk/docs/install
    2. gcloud auth application-default login --scopes=\\
         https://www.googleapis.com/auth/cloud-platform,\\
         https://www.googleapis.com/auth/webmasters.readonly
       (logs in as you; you must already have access to the GSC property)
    3. Enable "Search Console API" in your GCP project:
       https://console.cloud.google.com/apis/library/searchconsole.googleapis.com
    4. Set the quota project once:
       gcloud auth application-default set-quota-project YOUR-GCP-PROJECT-ID

  Mode B: Service account key (for servers or CI)
    1. Create a service account in GCP Console (no special roles).
    2. Download its JSON key. If your Workspace org blocks key creation, use Mode A.
    3. Enable "Search Console API" in the project.
    4. In Search Console, Settings > Users and permissions, add the
       service account email as a user with Full access.
    5. Export the path: export GSC_SA_KEY=/path/to/service-account.json

Usage:
  python3 gsc_pull.py --site sc-domain:example.com     # required
  python3 gsc_pull.py --site sc-domain:example.com --days 28
  python3 gsc_pull.py --site sc-domain:example.com --dry-run
  python3 gsc_pull.py --site sc-domain:example.com --key /path/to/sa.json

Output:
  ./data/gsc-YYYY-MM-DD.json    # dated snapshot
  ./data/gsc-latest.json        # stable filename for downstream dashboards

Part of the AI Visibility Monitor toolkit. Built by Ignacio Lopez (Work-Smart.ai).
MIT licensed. https://github.com/WorkSmartAI-alt/ai-visibility-monitor
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    from google.auth import default as google_auth_default  # type: ignore
    from google.auth.exceptions import DefaultCredentialsError  # type: ignore
    from google.oauth2 import service_account  # type: ignore
    from googleapiclient.discovery import build  # type: ignore
    from googleapiclient.errors import HttpError  # type: ignore
except ImportError:
    print(
        "ERROR: google API client libraries not installed.\n"
        "Run: pip3 install google-api-python-client google-auth",
        file=sys.stderr,
    )
    sys.exit(2)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_SITE = "sc-domain:example.com"
DEFAULT_DAYS = 28                                # rolling window size
DEFAULT_LAG_DAYS = 3                             # end date = today minus this
DEFAULT_ROW_LIMIT = 500                          # max rows per API call
DEFAULT_STRIKING_MIN_IMPRESSIONS = 50            # over the window
DEFAULT_STRIKING_POS_MIN = 5.0
DEFAULT_STRIKING_POS_MAX = 20.0

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


# LatAm country codes we care about for the Miami + LatAm positioning
LATAM_COUNTRIES = {
    "arg", "bra", "chl", "col", "mex", "per", "ury", "pry", "ecu", "ven", "bol",
    "cri", "pan", "dom", "gtm", "hnd", "slv", "nic", "pri", "cub",
}
ANCHOR_COUNTRIES = {"usa"}   # Miami / primary market


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def load_credentials(key_path: Path | None):
    """
    Two auth modes:

      1. Service account key (Mode B) if --key or GSC_SA_KEY is set.
      2. Application Default Credentials (Mode A) otherwise.

    Mode A covers `gcloud auth application-default login` for local use and
    metadata-server credentials when running inside GCP. Preferred for local
    work because no key file sits on disk.
    """
    if key_path is not None:
        if not key_path.exists():
            print(f"ERROR: service account key not found at {key_path}", file=sys.stderr)
            print("Unset GSC_SA_KEY to fall back to ADC, or fix the path.", file=sys.stderr)
            sys.exit(2)
        print(f"[gsc_pull] auth mode: service account key ({key_path})")
        return service_account.Credentials.from_service_account_file(str(key_path), scopes=SCOPES)

    try:
        creds, project = google_auth_default(scopes=SCOPES)
    except DefaultCredentialsError as e:
        print("ERROR: no credentials found. Two options:", file=sys.stderr)
        print("  A. Run `gcloud auth application-default login` to use your own account.", file=sys.stderr)
        print("  B. Export GSC_SA_KEY=/path/to/service-account.json for a service account.", file=sys.stderr)
        print(f"     underlying error: {e}", file=sys.stderr)
        sys.exit(2)
    project_hint = f" (project: {project})" if project else ""
    print(f"[gsc_pull] auth mode: application default credentials{project_hint}")
    return creds


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def run_query(svc, site: str, start: str, end: str, dimensions: list[str], row_limit: int) -> list[dict]:
    """One call to searchanalytics.query with the given dimensions."""
    body = {
        "startDate": start,
        "endDate": end,
        "dimensions": dimensions,
        "rowLimit": row_limit,
        "dataState": "final",   # exclude fresh/partial rows, keep trend stable
    }
    try:
        resp = svc.searchanalytics().query(siteUrl=site, body=body).execute()
    except HttpError as e:
        print(f"    API error on dimensions={dimensions}: {e}", file=sys.stderr)
        return []
    rows = resp.get("rows", []) or []
    out = []
    for r in rows:
        keys = r.get("keys", []) or []
        out.append({
            **{dim: keys[i] if i < len(keys) else None for i, dim in enumerate(dimensions)},
            "clicks": int(r.get("clicks", 0) or 0),
            "impressions": int(r.get("impressions", 0) or 0),
            "ctr": round(float(r.get("ctr", 0.0) or 0.0), 4),
            "position": round(float(r.get("position", 0.0) or 0.0), 2),
        })
    return out


# ---------------------------------------------------------------------------
# Derived views
# ---------------------------------------------------------------------------

def striking_distance(queries: list[dict], min_impr: int, pos_min: float, pos_max: float) -> list[dict]:
    """Queries where Google already ranks you 5 to 20 with enough impressions to matter."""
    out = []
    for q in queries:
        pos = q.get("position", 0.0)
        impr = q.get("impressions", 0)
        if pos_min <= pos <= pos_max and impr >= min_impr:
            out.append(q)
    # Sort by impressions descending so the biggest opportunities float up.
    out.sort(key=lambda x: x["impressions"], reverse=True)
    return out


def summarize(queries: list[dict]) -> dict:
    """Roll up the query list into headline metrics."""
    if not queries:
        return {"clicks": 0, "impressions": 0, "ctr": 0, "position_avg": 0, "queries_total": 0}
    total_clicks = sum(q["clicks"] for q in queries)
    total_impr = sum(q["impressions"] for q in queries)
    # Weighted averages so a query with 5000 impressions matters more than one with 5.
    pos_weighted = sum(q["position"] * q["impressions"] for q in queries) / total_impr if total_impr else 0
    ctr = total_clicks / total_impr if total_impr else 0
    return {
        "clicks": total_clicks,
        "impressions": total_impr,
        "ctr": round(ctr, 4),
        "position_avg": round(pos_weighted, 2),
        "queries_total": len(queries),
    }


def country_buckets(rows_by_country: list[dict]) -> dict:
    """Split country rows into US / LatAm / Other buckets."""
    buckets = {"usa": {"clicks": 0, "impressions": 0},
               "latam": {"clicks": 0, "impressions": 0},
               "other": {"clicks": 0, "impressions": 0}}
    for r in rows_by_country:
        c = (r.get("country") or "").lower()
        if c in ANCHOR_COUNTRIES:
            k = "usa"
        elif c in LATAM_COUNTRIES:
            k = "latam"
        else:
            k = "other"
        buckets[k]["clicks"] += r["clicks"]
        buckets[k]["impressions"] += r["impressions"]
    return buckets


def device_buckets(rows_by_device: list[dict]) -> dict:
    """Aggregate device rows (mobile/desktop/tablet)."""
    out = {"mobile": {"clicks": 0, "impressions": 0},
           "desktop": {"clicks": 0, "impressions": 0},
           "tablet": {"clicks": 0, "impressions": 0}}
    for r in rows_by_device:
        d = (r.get("device") or "").lower()
        if d in out:
            out[d]["clicks"] += r["clicks"]
            out[d]["impressions"] += r["impressions"]
    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default=DEFAULT_SITE, help="GSC property URL")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="Rolling window size in days")
    parser.add_argument("--lag-days", type=int, default=DEFAULT_LAG_DAYS, help="End date lag from today")
    parser.add_argument("--key", default=os.environ.get("GSC_SA_KEY"),
                        help="Path to service account JSON (or set GSC_SA_KEY env var)")
    parser.add_argument("--row-limit", type=int, default=DEFAULT_ROW_LIMIT, help="Max rows per API call")
    parser.add_argument("--striking-min-impressions", type=int, default=DEFAULT_STRIKING_MIN_IMPRESSIONS)
    parser.add_argument("--striking-pos-min", type=float, default=DEFAULT_STRIKING_POS_MIN)
    parser.add_argument("--striking-pos-max", type=float, default=DEFAULT_STRIKING_POS_MAX)
    parser.add_argument("--dry-run", action="store_true", help="Auth check only, no API call")
    parser.add_argument("--output-dir", default=None, help="Override output dir (default: ../data/)")
    args = parser.parse_args()

    key_path = Path(args.key).expanduser().resolve() if args.key else None

    here = Path(__file__).resolve().parent
    output_dir = Path(args.output_dir) if args.output_dir else (here / "data")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Date window
    end_d = date.today() - timedelta(days=args.lag_days)
    start_d = end_d - timedelta(days=args.days - 1)
    start_s = start_d.isoformat()
    end_s = end_d.isoformat()

    print(f"[gsc_pull] site: {args.site}")
    print(f"[gsc_pull] window: {start_s} to {end_s} ({args.days} days)")

    creds = load_credentials(key_path)

    if args.dry_run:
        print("[dry-run] credentials loaded OK, skipping API calls.")
        return 0

    svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)

    # Quick sanity check: confirm the service account has access to this site.
    try:
        sites = svc.sites().list().execute()
        site_entries = sites.get("siteEntry", []) or []
        available = [s.get("siteUrl") for s in site_entries]
        if args.site not in available:
            print(f"WARN: {args.site} not in this service account's GSC properties.", file=sys.stderr)
            print(f"      Available: {available}", file=sys.stderr)
            print("      Grant access in Search Console > Settings > Users and permissions.", file=sys.stderr)
            # continue anyway, API will fail clearly
    except HttpError as e:
        print(f"WARN: could not list GSC sites: {e}", file=sys.stderr)

    t0 = time.perf_counter()

    print("[gsc_pull] pulling by query...")
    rows_query = run_query(svc, args.site, start_s, end_s, ["query"], args.row_limit)
    print(f"    {len(rows_query)} queries")

    print("[gsc_pull] pulling by page...")
    rows_page = run_query(svc, args.site, start_s, end_s, ["page"], args.row_limit)
    print(f"    {len(rows_page)} pages")

    print("[gsc_pull] pulling by query + country...")
    rows_country = run_query(svc, args.site, start_s, end_s, ["query", "country"], args.row_limit)
    print(f"    {len(rows_country)} query+country rows")

    print("[gsc_pull] pulling by query + device...")
    rows_device = run_query(svc, args.site, start_s, end_s, ["query", "device"], args.row_limit)
    print(f"    {len(rows_device)} query+device rows")

    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    # Derived views
    summary = summarize(rows_query)
    striking = striking_distance(
        rows_query,
        args.striking_min_impressions,
        args.striking_pos_min,
        args.striking_pos_max,
    )
    countries = country_buckets(rows_country)
    devices = device_buckets(rows_device)

    bundle = {
        "run_date_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "generator": "gsc_pull.py",
        "version": "1.0",
        "site": args.site,
        "window": {"start": start_s, "end": end_s, "days": args.days, "lag_days": args.lag_days},
        "summary": summary,
        "countries": countries,
        "devices": devices,
        "striking_distance": {
            "criteria": {
                "position_range": [args.striking_pos_min, args.striking_pos_max],
                "min_impressions": args.striking_min_impressions,
            },
            "queries": striking[:50],    # cap for readability, full list is in raw
        },
        "top_queries": rows_query[:50],
        "top_pages": rows_page[:50],
        "raw": {
            "by_query": rows_query,
            "by_page": rows_page,
            "by_query_country": rows_country,
            "by_query_device": rows_device,
        },
        "timing_ms": elapsed_ms,
    }

    run_date = bundle["run_date_utc"]
    out_path = output_dir / f"gsc-{run_date}.json"
    out_path.write_text(json.dumps(bundle, indent=2, default=str), encoding="utf-8")
    (output_dir / "gsc-latest.json").write_text(json.dumps(bundle, indent=2, default=str), encoding="utf-8")

    # Terminal summary so the story is visible at a glance
    print()
    print("=" * 60)
    print(f"GSC PULL · {run_date} · {args.site}")
    print("=" * 60)
    print(f"Window: {start_s} to {end_s} ({args.days} days)")
    print(f"Clicks: {summary['clicks']}  |  Impressions: {summary['impressions']}  |  CTR: {summary['ctr']*100:.2f}%  |  Avg position: {summary['position_avg']}")
    print(f"Countries: USA {countries['usa']['clicks']} clicks  |  LatAm {countries['latam']['clicks']} clicks  |  Other {countries['other']['clicks']} clicks")
    print(f"Devices: Mobile {devices['mobile']['clicks']}  |  Desktop {devices['desktop']['clicks']}  |  Tablet {devices['tablet']['clicks']} clicks")
    print()
    print(f"Top 10 queries by clicks:")
    for q in sorted(rows_query, key=lambda x: x["clicks"], reverse=True)[:10]:
        print(f"  {q['clicks']:>4}c  {q['impressions']:>6}i  pos {q['position']:>5.2f}   {q['query']}")
    print()
    print(f"Striking-distance queries (position {args.striking_pos_min}-{args.striking_pos_max}, "
          f">= {args.striking_min_impressions} impressions): {len(striking)}")
    for q in striking[:10]:
        print(f"  pos {q['position']:>5.2f}  {q['impressions']:>6}i  {q['clicks']:>3}c   {q['query']}")
    print()
    print(f"JSON: {out_path}")
    print(f"JSON: {output_dir / 'gsc-latest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
