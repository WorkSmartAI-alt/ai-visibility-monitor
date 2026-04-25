# AI Visibility Monitor

A small toolkit for tracking whether your website appears in AI search results (ChatGPT, Claude, Perplexity, Gemini) and Google search, and for diagnosing the technical layer underneath that determines whether AI engines can read your site at all.

Four Python scripts. No SaaS, no dashboard service to subscribe to. You run them locally on your own credentials, the JSON output is yours, and you can pipe it into whatever dashboard or report you already use.

Built for solo operators and small consulting practices who need real visibility data without a $500-per-seat enterprise tool.

## What's in here

| Script | What it does | Cadence | Credentials |
|---|---|---|---|
| `prereqs_sweep.py` | Checks robots.txt, llms.txt, sitemap.xml, and AI bot permissions for any list of sites | Monthly | None |
| `citation_check.py` | Asks Claude buyer-style questions with web_search enabled, records every URL Claude cites, flags whether your domain appears | Monthly | Anthropic API key |
| `gsc_pull.py` | Pulls Google Search Console data: top queries, top pages, country and device splits, striking-distance queries (position 5-20 with meaningful impressions) | Weekly | Google ADC |
| `ga4_pull.py` | Pulls Google Analytics 4 data: sessions, engagement, traffic channels, **AI-referral cut** (sessions from chatgpt.com, claude.ai, perplexity.ai, gemini.google.com, copilot.microsoft.com) | Weekly | Google ADC |

The AI-referral cut in `ga4_pull.py` is the only direct measure of whether AI citations convert to actual website visits. Citations are a leading indicator. AI referrals are the lagging one.

## Quick start

```bash
# 1. Clone
git clone https://github.com/WorkSmartAI-alt/ai-visibility-monitor.git
cd ai-visibility-monitor

# 2. Install Python deps (only what each script you'll use needs)
pip3 install anthropic                            # for citation_check.py
pip3 install google-api-python-client google-auth # for gsc_pull.py
pip3 install google-analytics-data                # for ga4_pull.py
# prereqs_sweep.py needs no deps beyond stdlib

# 3. Configure your sites
cp sites.json.example sites.json
# edit sites.json with your domains

# 4. Configure your buyer queries
cp queries.md.example queries.md
# edit queries.md with the 5 buyer queries you want to track

# 5. Run the no-credentials script first to confirm the toolchain works
python3 prereqs_sweep.py

# 6. Configure credentials, then run the full suite (see docs below)
python3 citation_check.py
python3 gsc_pull.py
python3 ga4_pull.py
```

Outputs land in `./data/`. Each script writes both a dated snapshot (`gsc-2026-04-25.json`) and a stable `-latest.json` filename so any dashboard layer pointed at this folder always reads the most recent run.

## Why these four scripts (and not more)

There are five things that determine whether your site shows up in AI-generated answers:

1. **Crawlability.** AI bots have to be allowed through robots.txt, and they have to find your URLs through a working sitemap. `prereqs_sweep.py` checks this.
2. **Citation rate.** When a buyer asks a question your business is supposed to answer, does your domain actually appear in the cited sources? `citation_check.py` measures this directly against Claude with web_search.
3. **Search performance.** Google rankings are still the strongest input to AI engine training data. `gsc_pull.py` tracks how Google sees you.
4. **Traffic conversion.** When AI engines and Google do send you traffic, does it engage and convert? `ga4_pull.py` covers this, with the AI-referral cut singled out so the GEO signal does not get buried in normal traffic.
5. **Page performance (Core Web Vitals).** Slow pages are deprioritized by both Google and AI crawlers. A `psi_pull.py` for PageSpeed Insights is on the roadmap (issues welcome).

Together these four answer the operator's question: am I showing up where my buyers look, and if not, where exactly is the breakdown?

## What each output JSON looks like

See `sample-data/` for fully-anonymized example outputs from each script. You can use these to build a dashboard against the schema before you've run the scripts on your own data.

## Authentication

### `citation_check.py` (Anthropic API)

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
python3 citation_check.py
```

### `gsc_pull.py` and `ga4_pull.py` (Google ADC)

The recommended path is Application Default Credentials via the gcloud CLI. This avoids storing service account keys on disk and is allowed even when your Workspace org blocks key creation.

```bash
# install gcloud CLI: https://cloud.google.com/sdk/docs/install

gcloud auth application-default login \
  --scopes=https://www.googleapis.com/auth/cloud-platform,\
https://www.googleapis.com/auth/webmasters.readonly,\
https://www.googleapis.com/auth/analytics.readonly

gcloud auth application-default set-quota-project YOUR-GCP-PROJECT-ID
```

Enable the two APIs in your project:

- Search Console API: https://console.cloud.google.com/apis/library/searchconsole.googleapis.com
- GA4 Data API: https://console.cloud.google.com/apis/library/analyticsdata.googleapis.com

If your Workspace organization blocks the default Cloud SDK OAuth client (you'll see a "this app is blocked" page), create your own OAuth client (Desktop type) in your GCP project and pass it via:

```bash
gcloud auth application-default login --client-id-file=PATH/TO/your-oauth-client.json --scopes=...
```

### Service account alternative

If you'd rather use service account keys (for CI/CD or unattended runs), set:

```bash
export GSC_SA_KEY=/path/to/service-account.json
```

The service account email needs Full access on the GSC property and at least Viewer access on the GA4 property.

## Recommended cadence

- **Monthly:** `prereqs_sweep.py` and `citation_check.py`. Citation comparisons need 2-8 weeks to be meaningful, weekly is too noisy.
- **Weekly:** `gsc_pull.py` and `ga4_pull.py`. Search and traffic data move week-to-week; monthly loses signal.
- **Ad-hoc:** any script after a deploy that changes routing, redirects, robots.txt, or sitemap.

## Schedule it

A simple crontab covers all four:

```cron
# Monthly (1st of month, 09:00 ET)
0 9 1 * * cd /path/to/repo && python3 prereqs_sweep.py
0 9 1 * * cd /path/to/repo && python3 citation_check.py

# Weekly (Mondays 09:00 ET)
0 9 * * 1 cd /path/to/repo && python3 gsc_pull.py
0 9 * * 1 cd /path/to/repo && python3 ga4_pull.py
```

## Why I built this

I'm a fractional Head of AI for mid-market companies. Most of my clients want to know: "are we showing up when our buyers ask AI tools about our category?" Existing AEO/GEO monitoring tools start at $300-500/month per site, which doesn't make sense for a 4-site portfolio.

So I built this. It runs locally, costs nothing beyond your Anthropic API spend (about $1-3 per citation check run), and the JSON output is yours to do whatever with.

If you want the strategic context behind why citation tracking matters for mid-market AI consulting, see https://work-smart.ai/blog/how-to-get-cited-by-ai-search.

If your team needs help building this into a fuller monitoring stack or wiring it into a custom dashboard, work-smart.ai/services/ai-visibility.

## Contributing

Issues and PRs welcome. Especially helpful: 

- A `psi_pull.py` for Core Web Vitals (PageSpeed Insights API)
- Support for Bing Webmaster Tools alongside GSC
- Postgres or DuckDB output instead of JSON files
- Per-bot user-agent testing in `prereqs_sweep.py` (currently uses one generic UA)

See CONTRIBUTING.md.

## License

MIT. Use it, fork it, build a SaaS on top of it. Attribution appreciated but not required.

---

Built by [Ignacio Lopez](https://www.linkedin.com/in/ignaciolopez2017/), [Work-Smart.ai](https://work-smart.ai). Originally part of an internal monitoring stack for Work-Smart's AI visibility work with mid-market clients.
