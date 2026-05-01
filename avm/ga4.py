from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    from google.analytics.data_v1beta import BetaAnalyticsDataClient  # type: ignore
    from google.analytics.data_v1beta.types import (  # type: ignore
        DateRange, Dimension, Metric, RunReportRequest, OrderBy,
    )
    from google.auth import default as google_auth_default  # type: ignore
    from google.auth.exceptions import DefaultCredentialsError  # type: ignore
except ImportError:
    print(
        "ERROR: GA4 Data API client not installed.\n"
        "Run: pip install google-analytics-data google-auth",
        file=sys.stderr,
    )
    sys.exit(2)

DEFAULT_DAYS = 28
DEFAULT_LAG_DAYS = 2
DEFAULT_ROW_LIMIT = 100

SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]

AI_REFERRER_DOMAINS = {
    "chatgpt.com", "chat.openai.com", "claude.ai", "perplexity.ai",
    "www.perplexity.ai", "gemini.google.com", "copilot.microsoft.com",
    "you.com", "poe.com", "phind.com",
}

LATAM_COUNTRIES = {
    "Argentina", "Brazil", "Chile", "Colombia", "Mexico", "Peru", "Uruguay",
    "Paraguay", "Ecuador", "Venezuela", "Bolivia", "Costa Rica", "Panama",
    "Dominican Republic", "Guatemala", "Honduras", "El Salvador", "Nicaragua",
    "Puerto Rico", "Cuba",
}
ANCHOR_COUNTRIES = {"United States"}


def _get_client() -> BetaAnalyticsDataClient:
    try:
        creds, project = google_auth_default(scopes=SCOPES)
    except DefaultCredentialsError as e:
        print("ERROR: no credentials found. Run:", file=sys.stderr)
        print("  gcloud auth application-default login", file=sys.stderr)
        print(f"  underlying: {e}", file=sys.stderr)
        sys.exit(2)
    hint = f" (project: {project})" if project else ""
    print(f"[ga4_pull] auth mode: application default credentials{hint}")
    return BetaAnalyticsDataClient(credentials=creds)


def _run_report(client, property_id, start, end, metrics, dimensions=None, order_by=None, limit=DEFAULT_ROW_LIMIT):
    req = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=start, end_date=end)],
        metrics=[Metric(name=m) for m in metrics],
        dimensions=[Dimension(name=d) for d in (dimensions or [])],
        order_bys=order_by or [],
        limit=limit,
    )
    resp = client.run_report(req)
    out = []
    for row in resp.rows:
        r: dict = {}
        for i, dim in enumerate(dimensions or []):
            r[dim] = row.dimension_values[i].value
        for i, m in enumerate(metrics):
            v = row.metric_values[i].value
            try:
                r[m] = float(v) if "." in v or "e" in v.lower() else int(v)
            except (ValueError, TypeError):
                r[m] = v
        out.append(r)
    return out


def _extract_summary(rows: list[dict]) -> dict:
    if not rows:
        return {"sessions": 0, "totalUsers": 0, "activeUsers": 0,
                "engagedSessions": 0, "newUsers": 0, "engagementRate": 0, "conversions": 0}
    r = rows[0]
    return {
        "sessions": r.get("sessions", 0),
        "totalUsers": r.get("totalUsers", 0),
        "activeUsers": r.get("activeUsers", 0),
        "engagedSessions": r.get("engagedSessions", 0),
        "newUsers": r.get("newUsers", 0),
        "engagementRate": round(float(r.get("engagementRate", 0)), 4),
        "conversions": r.get("conversions", 0),
    }


def _ai_referrer_cut(source_rows: list[dict]) -> dict:
    ai_rows = []
    total_sessions = 0
    total_users = 0
    for r in source_rows:
        src = (r.get("sessionSource") or "").lower().strip()
        if src in AI_REFERRER_DOMAINS:
            ai_rows.append({"source": src, "sessions": r.get("sessions", 0), "totalUsers": r.get("totalUsers", 0)})
            total_sessions += r.get("sessions", 0)
            total_users += r.get("totalUsers", 0)
    ai_rows.sort(key=lambda x: x["sessions"], reverse=True)
    return {"total_sessions": total_sessions, "total_users": total_users, "breakdown": ai_rows}


def _country_buckets(rows: list[dict]) -> dict:
    b = {"usa": {"sessions": 0}, "latam": {"sessions": 0}, "other": {"sessions": 0}}
    for r in rows:
        c = r.get("country", "")
        k = "usa" if c in ANCHOR_COUNTRIES else ("latam" if c in LATAM_COUNTRIES else "other")
        b[k]["sessions"] += r.get("sessions", 0)
    return b


def _device_buckets(rows: list[dict]) -> dict:
    out = {"desktop": 0, "mobile": 0, "tablet": 0, "smart tv": 0, "other": 0}
    for r in rows:
        d = (r.get("deviceCategory") or "other").lower()
        out[d if d in out else "other"] = out.get(d if d in out else "other", 0) + r.get("sessions", 0)
    return out


def run_ga4_pull(
    property_id: str,
    days: int = DEFAULT_DAYS,
    credentials_path: str | None = None,
) -> dict:
    """
    Pull Google Analytics 4 data for a GA4 property.

    Returns the GA4 data dict with AI-referrer slice (same shape as v0.1.0 JSON output).
    """
    pid = str(property_id).strip()
    client = _get_client()

    lag_days = DEFAULT_LAG_DAYS
    end_d = date.today() - timedelta(days=lag_days)
    start_d = end_d - timedelta(days=days - 1)
    start_s, end_s = start_d.isoformat(), end_d.isoformat()

    t0 = time.perf_counter()

    print("[ga4_pull] 1/7 summary metrics...")
    summary_rows = _run_report(
        client, pid, start_s, end_s,
        metrics=["sessions", "totalUsers", "activeUsers", "engagedSessions",
                 "newUsers", "engagementRate", "conversions"],
    )
    summary = _extract_summary(summary_rows)
    print(f"    sessions: {summary['sessions']} · users: {summary['totalUsers']} · engaged: {summary['engagedSessions']}")

    print("[ga4_pull] 2/7 top landing pages...")
    landing = _run_report(
        client, pid, start_s, end_s,
        metrics=["sessions", "activeUsers", "engagementRate"],
        dimensions=["landingPage"],
        order_by=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=50,
    )
    print(f"    {len(landing)} landing pages")

    print("[ga4_pull] 3/7 channel + source...")
    channels = _run_report(
        client, pid, start_s, end_s,
        metrics=["sessions", "totalUsers"],
        dimensions=["sessionDefaultChannelGroup"],
        order_by=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
    )
    sources = _run_report(
        client, pid, start_s, end_s,
        metrics=["sessions", "totalUsers"],
        dimensions=["sessionSource", "sessionMedium"],
        order_by=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=100,
    )
    print(f"    {len(channels)} channels · {len(sources)} source+medium combos")

    print("[ga4_pull] 4/7 AI referrer cut (computed from sources)...")
    ai_refs = _ai_referrer_cut(sources)
    print(f"    AI referrals: {ai_refs['total_sessions']} sessions from {len(ai_refs['breakdown'])} AI sources")

    print("[ga4_pull] 5/7 country split...")
    countries_raw = _run_report(
        client, pid, start_s, end_s,
        metrics=["sessions"],
        dimensions=["country"],
        order_by=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=100,
    )
    countries = _country_buckets(countries_raw)
    print(f"    USA {countries['usa']['sessions']}  |  LatAm {countries['latam']['sessions']}  |  Other {countries['other']['sessions']}")

    print("[ga4_pull] 6/7 device split...")
    devices_raw = _run_report(
        client, pid, start_s, end_s,
        metrics=["sessions"],
        dimensions=["deviceCategory"],
    )
    devices = _device_buckets(devices_raw)
    print(f"    desktop {devices['desktop']}  |  mobile {devices['mobile']}  |  tablet {devices['tablet']}")

    print("[ga4_pull] 7/7 top events...")
    events = _run_report(
        client, pid, start_s, end_s,
        metrics=["eventCount", "conversions"],
        dimensions=["eventName"],
        order_by=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="eventCount"), desc=True)],
        limit=30,
    )
    conversion_events = [e for e in events if e.get("conversions", 0) > 0]
    print(f"    {len(events)} events total · {len(conversion_events)} marked as conversions")

    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    return {
        "run_date_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "generator": "ga4_pull.py",
        "version": "1.0",
        "property_id": pid,
        "window": {"start": start_s, "end": end_s, "days": days, "lag_days": lag_days},
        "summary": summary,
        "ai_referrals": ai_refs,
        "channels": channels,
        "countries": countries,
        "devices": devices,
        "top_landing_pages": landing[:20],
        "top_sources": sources[:30],
        "top_events": events[:20],
        "conversion_events": conversion_events,
        "raw": {
            "landing_pages": landing,
            "channels": channels,
            "sources": sources,
            "countries": countries_raw,
            "devices": devices_raw,
            "events": events,
        },
        "timing_ms": elapsed_ms,
    }


def main_cli() -> int:
    from avm.output import write_json

    parser = argparse.ArgumentParser(description="AI Visibility Monitor - GA4 pull")
    parser.add_argument("--property", default=os.environ.get("GA4_PROPERTY_ID"),
                        help="GA4 property ID (numeric). Or set GA4_PROPERTY_ID env var.")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--row-limit", type=int, default=DEFAULT_ROW_LIMIT)
    parser.add_argument("--dry-run", action="store_true", help="Auth check only")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    if not args.property:
        print("ERROR: no GA4 property ID provided.", file=sys.stderr)
        print("Pass --property 123456789 or export GA4_PROPERTY_ID=123456789", file=sys.stderr)
        return 2
    property_id = str(args.property).strip()

    here = Path(__file__).resolve().parent.parent
    output_dir = Path(args.output_dir) if args.output_dir else (here / "data")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[ga4_pull] property: {property_id}")

    if args.dry_run:
        _get_client()
        print("[dry-run] client initialized OK, skipping API calls.")
        return 0

    bundle = run_ga4_pull(property_id=property_id, days=args.days)
    run_date = bundle["run_date_utc"]
    out_path = output_dir / f"ga4-{run_date}.json"
    write_json(bundle, out_path)

    summary = bundle["summary"]
    ai_refs = bundle["ai_referrals"]
    channels = bundle["channels"]
    landing = bundle["top_landing_pages"]
    events = bundle["top_events"]
    window = bundle["window"]

    print()
    print("=" * 60)
    print(f"GA4 PULL · {run_date} · property {property_id}")
    print("=" * 60)
    print(f"Window: {window['start']} to {window['end']} ({window['days']} days)")
    print(
        f"Sessions: {summary['sessions']}  |  Users: {summary['totalUsers']}  |  "
        f"Engaged: {summary['engagedSessions']}  |  Engagement rate: {summary['engagementRate']*100:.1f}%"
    )
    print(f"Conversions: {summary['conversions']}")
    print()
    print("AI referrals (the GEO signal):")
    if ai_refs["total_sessions"] == 0:
        print("  none yet. Expected at this stage; citations have to appear first.")
    else:
        print(f"  {ai_refs['total_sessions']} sessions total from {len(ai_refs['breakdown'])} AI sources")
        for r in ai_refs["breakdown"][:5]:
            print(f"    {r['sessions']:>4} sessions  {r['source']}")
    print()
    print("Top 5 channels by sessions:")
    for c in channels[:5]:
        print(f"  {c['sessions']:>5}s  {c['totalUsers']:>5}u  {c.get('sessionDefaultChannelGroup', '(not set)')}")
    print()
    print("Top 5 landing pages by sessions:")
    for p in landing[:5]:
        path = p.get("landingPage") or "(not set)"
        path = path if len(path) <= 60 else path[:60] + "..."
        print(f"  {p['sessions']:>4}s  {p['activeUsers']:>4}u  {path}")
    print()
    print("Top 5 events:")
    for e in events[:5]:
        conv_tag = " (conversion)" if e.get("conversions", 0) > 0 else ""
        print(f"  {e['eventCount']:>5}  {e.get('eventName', '(not set)')}{conv_tag}")
    print()
    print(f"JSON: {out_path}")
    print(f"JSON: {output_dir / 'ga4-latest.json'}")
    return 0
