from __future__ import annotations

import argparse
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
        "Run: pip install google-api-python-client google-auth",
        file=sys.stderr,
    )
    sys.exit(2)

DEFAULT_DAYS = 28
DEFAULT_LAG_DAYS = 3
DEFAULT_ROW_LIMIT = 500
DEFAULT_STRIKING_MIN_IMPRESSIONS = 50
DEFAULT_STRIKING_POS_MIN = 5.0
DEFAULT_STRIKING_POS_MAX = 20.0

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

LATAM_COUNTRIES = {
    "arg", "bra", "chl", "col", "mex", "per", "ury", "pry", "ecu", "ven", "bol",
    "cri", "pan", "dom", "gtm", "hnd", "slv", "nic", "pri", "cub",
}
ANCHOR_COUNTRIES = {"usa"}


def _load_credentials(key_path: Path | None):
    if key_path is not None:
        if not key_path.exists():
            print(f"ERROR: service account key not found at {key_path}", file=sys.stderr)
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
    hint = f" (project: {project})" if project else ""
    print(f"[gsc_pull] auth mode: application default credentials{hint}")
    return creds


def _query(svc, site: str, start: str, end: str, dimensions: list[str], row_limit: int) -> list[dict]:
    body = {
        "startDate": start,
        "endDate": end,
        "dimensions": dimensions,
        "rowLimit": row_limit,
        "dataState": "final",
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


def _striking_distance(queries: list[dict], min_impr: int, pos_min: float, pos_max: float) -> list[dict]:
    out = [
        q for q in queries
        if pos_min <= q.get("position", 0.0) <= pos_max and q.get("impressions", 0) >= min_impr
    ]
    out.sort(key=lambda x: x["impressions"], reverse=True)
    return out


def _summarize(queries: list[dict]) -> dict:
    if not queries:
        return {"clicks": 0, "impressions": 0, "ctr": 0, "position_avg": 0, "queries_total": 0}
    total_clicks = sum(q["clicks"] for q in queries)
    total_impr = sum(q["impressions"] for q in queries)
    pos_weighted = sum(q["position"] * q["impressions"] for q in queries) / total_impr if total_impr else 0
    ctr = total_clicks / total_impr if total_impr else 0
    return {
        "clicks": total_clicks,
        "impressions": total_impr,
        "ctr": round(ctr, 4),
        "position_avg": round(pos_weighted, 2),
        "queries_total": len(queries),
    }


def _country_buckets(rows: list[dict]) -> dict:
    buckets = {
        "usa": {"clicks": 0, "impressions": 0},
        "latam": {"clicks": 0, "impressions": 0},
        "other": {"clicks": 0, "impressions": 0},
    }
    for r in rows:
        c = (r.get("country") or "").lower()
        k = "usa" if c in ANCHOR_COUNTRIES else ("latam" if c in LATAM_COUNTRIES else "other")
        buckets[k]["clicks"] += r["clicks"]
        buckets[k]["impressions"] += r["impressions"]
    return buckets


def _device_buckets(rows: list[dict]) -> dict:
    out = {
        "mobile": {"clicks": 0, "impressions": 0},
        "desktop": {"clicks": 0, "impressions": 0},
        "tablet": {"clicks": 0, "impressions": 0},
    }
    for r in rows:
        d = (r.get("device") or "").lower()
        if d in out:
            out[d]["clicks"] += r["clicks"]
            out[d]["impressions"] += r["impressions"]
    return out


def run_gsc_pull(
    domain: str,
    days: int = DEFAULT_DAYS,
    credentials_path: str | None = None,
) -> dict:
    """
    Pull Google Search Console performance data for a GSC property.

    domain: GSC site URL, e.g. "sc-domain:example.com" or "https://example.com/"
    Returns the GSC data dict (same shape as v0.1.0 JSON output).
    """
    site = domain if domain.startswith("sc-domain:") or domain.startswith("http") else f"sc-domain:{domain}"
    key_path = Path(credentials_path).expanduser().resolve() if credentials_path else None
    creds = _load_credentials(key_path)

    lag_days = DEFAULT_LAG_DAYS
    end_d = date.today() - timedelta(days=lag_days)
    start_d = end_d - timedelta(days=days - 1)
    start_s, end_s = start_d.isoformat(), end_d.isoformat()

    svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)

    try:
        sites_list = svc.sites().list().execute()
        available = [s.get("siteUrl") for s in (sites_list.get("siteEntry", []) or [])]
        if site not in available:
            print(f"WARN: {site} not in this service account's GSC properties.", file=sys.stderr)
            print(f"      Available: {available}", file=sys.stderr)
    except HttpError as e:
        print(f"WARN: could not list GSC sites: {e}", file=sys.stderr)

    t0 = time.perf_counter()
    row_limit = DEFAULT_ROW_LIMIT

    print("[gsc_pull] pulling by query...")
    rows_query = _query(svc, site, start_s, end_s, ["query"], row_limit)
    print(f"    {len(rows_query)} queries")

    print("[gsc_pull] pulling by page...")
    rows_page = _query(svc, site, start_s, end_s, ["page"], row_limit)
    print(f"    {len(rows_page)} pages")

    print("[gsc_pull] pulling by query + country...")
    rows_country = _query(svc, site, start_s, end_s, ["query", "country"], row_limit)
    print(f"    {len(rows_country)} query+country rows")

    print("[gsc_pull] pulling by query + device...")
    rows_device = _query(svc, site, start_s, end_s, ["query", "device"], row_limit)
    print(f"    {len(rows_device)} query+device rows")

    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    summary = _summarize(rows_query)
    striking = _striking_distance(
        rows_query,
        DEFAULT_STRIKING_MIN_IMPRESSIONS,
        DEFAULT_STRIKING_POS_MIN,
        DEFAULT_STRIKING_POS_MAX,
    )
    countries = _country_buckets(rows_country)
    devices = _device_buckets(rows_device)

    return {
        "run_date_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "generator": "gsc_pull.py",
        "version": "1.0",
        "site": site,
        "window": {"start": start_s, "end": end_s, "days": days, "lag_days": lag_days},
        "summary": summary,
        "countries": countries,
        "devices": devices,
        "striking_distance": {
            "criteria": {
                "position_range": [DEFAULT_STRIKING_POS_MIN, DEFAULT_STRIKING_POS_MAX],
                "min_impressions": DEFAULT_STRIKING_MIN_IMPRESSIONS,
            },
            "queries": striking[:50],
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


def main_cli() -> int:
    from avm.output import write_json

    parser = argparse.ArgumentParser(description="AI Visibility Monitor - GSC pull")
    parser.add_argument("--site", default="sc-domain:example.com", help="GSC property URL")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--key", default=os.environ.get("GSC_SA_KEY"), help="Service account JSON key path")
    parser.add_argument("--row-limit", type=int, default=DEFAULT_ROW_LIMIT)
    parser.add_argument("--dry-run", action="store_true", help="Auth check only, no API calls")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    key_path = Path(args.key).expanduser().resolve() if args.key else None
    here = Path(__file__).resolve().parent.parent
    output_dir = Path(args.output_dir) if args.output_dir else (here / "data")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[gsc_pull] site: {args.site}")

    if args.dry_run:
        _load_credentials(key_path)
        print("[dry-run] credentials loaded OK, skipping API calls.")
        return 0

    bundle = run_gsc_pull(domain=args.site, credentials_path=str(key_path) if key_path else None)
    run_date = bundle["run_date_utc"]
    out_path = output_dir / f"gsc-{run_date}.json"
    write_json(bundle, out_path)

    summary = bundle["summary"]
    countries = bundle["countries"]
    devices = bundle["devices"]
    rows_query = bundle["raw"]["by_query"]
    striking = bundle["striking_distance"]["queries"]
    window = bundle["window"]

    print()
    print("=" * 60)
    print(f"GSC PULL · {run_date} · {args.site}")
    print("=" * 60)
    print(f"Window: {window['start']} to {window['end']} ({window['days']} days)")
    print(
        f"Clicks: {summary['clicks']}  |  Impressions: {summary['impressions']}  |  "
        f"CTR: {summary['ctr']*100:.2f}%  |  Avg position: {summary['position_avg']}"
    )
    print(
        f"Countries: USA {countries['usa']['clicks']} clicks  |  "
        f"LatAm {countries['latam']['clicks']} clicks  |  Other {countries['other']['clicks']} clicks"
    )
    print(
        f"Devices: Mobile {devices['mobile']['clicks']}  |  "
        f"Desktop {devices['desktop']['clicks']}  |  Tablet {devices['tablet']['clicks']} clicks"
    )
    print()
    print("Top 10 queries by clicks:")
    for q in sorted(rows_query, key=lambda x: x["clicks"], reverse=True)[:10]:
        print(f"  {q['clicks']:>4}c  {q['impressions']:>6}i  pos {q['position']:>5.2f}   {q['query']}")
    print()
    print(f"Striking-distance queries (position {DEFAULT_STRIKING_POS_MIN}-{DEFAULT_STRIKING_POS_MAX}, "
          f">= {DEFAULT_STRIKING_MIN_IMPRESSIONS} impressions): {len(striking)}")
    for q in striking[:10]:
        print(f"  pos {q['position']:>5.2f}  {q['impressions']:>6}i  {q['clicks']:>3}c   {q['query']}")
    print()
    print(f"JSON: {out_path}")
    print(f"JSON: {output_dir / 'gsc-latest.json'}")
    return 0
