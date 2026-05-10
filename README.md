<p align="center">
  <img src="assets/banner.svg" alt="AI Visibility Monitor by Work-Smart.ai" width="100%">
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/WorkSmartAI-alt/ai-visibility-monitor?color=B08D3E&style=flat-square" alt="MIT License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square" alt="Python 3.10+"></a>
  <a href="https://github.com/WorkSmartAI-alt/ai-visibility-monitor/stargazers"><img src="https://img.shields.io/github/stars/WorkSmartAI-alt/ai-visibility-monitor?style=flat-square" alt="GitHub stars"></a>
  <a href="https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues"><img src="https://img.shields.io/github/issues/WorkSmartAI-alt/ai-visibility-monitor?style=flat-square" alt="Open issues"></a>
  <a href="https://theresanaiforthat.com/ai/ai-visibility-monitor-by-work-smart-ai/"><img src="https://img.shields.io/badge/Featured-TAAFT-B08D3E?style=flat-square" alt="Featured on TAAFT"></a>
</p>

**Most tools tell you if AI cites you. This tells you which queries you can win and what to make.**

Your buyers are asking ChatGPT, Claude, and Perplexity for recommendations. AVM is the open-source CLI that runs your buyer queries against all three, scores adjacent queries you can realistically win in 30 to 60 days, classifies which surfaces drive citations in your category (press, blog, forum, community), and tracks your visibility trajectory week over week.

Free, no signup, no SaaS upsell. Customer keeps all data. Multi-engine in a single command, ~$0.30 per weekly run.

[Quick Start ↓](#quick-start)

<p align="center">
  <img src="assets/pretty-output.png" alt="AI Visibility Monitor demo: pretty-printed terminal output showing 0 of 5 queries cited, top competitors per query" width="100%">
</p>

## Table of contents

- [Why this exists](#why-this-exists)
- [Quick start](#quick-start)
- [What you get](#what-you-get)
- [Prospect audit (avm audit-prospect)](#prospect-audit-avm-audit-prospect)
- [Adjacent query discovery (--expand)](#adjacent-query-discovery---expand)
- [Source-surface categorization](#source-surface-categorization)
- [Community threads (avm threads)](#community-threads-avm-threads)
- [Vertical baselines](#vertical-baselines)
- [Citation trajectory (avm trend)](#citation-trajectory-avm-trend)
- [How it works](#how-it-works)
- [Configuration](#configuration)
- [Authentication](#authentication)
- [How this compares](#how-this-compares)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)
- [Built by](#built-by)

## Why this exists

A growing share of B2B buyer research now starts inside an AI engine, not Google. ChatGPT, Claude, Perplexity, and Google AI Overviews answer category questions ("best CRM for mid-market construction") with a synthesized response and a list of cited sources. The companies named in those responses become the shortlist before a human ever lands on a website.

Most B2B sites have never measured whether they show up in that response. The few that try usually rely on enterprise SaaS tools at $29 to $499 per month with vendor-managed dashboards.

This tool is the cheapest version of that check. Five queries × three engines, a few minutes of run time, ~$0.30 in API costs per run on the default model. Yours forever, runs on your own credentials, nothing routes through a third-party server.

## Quick start

```bash
pip install ai-visibility-monitor
avm
```

That's it. On first run, the wizard walks you through:
1. Installing any missing dependencies (one keystroke)
2. Setting your Anthropic API key (saves to `.env` so you don't have to re-enter)
3. Picking your domain and competitors
4. Entering 5 buyer queries

Then it runs the citation check across Claude, ChatGPT, and Perplexity (whichever providers you have keys for).

Subsequent runs skip the wizard. Just run `avm` and the citation check executes against your saved config.

### Manual config (optional)

If you'd rather edit files directly:

```bash
git clone https://github.com/WorkSmartAI-alt/ai-visibility-monitor
cd ai-visibility-monitor
pip install -e .
cp queries.md.example queries.md     # edit your 5 queries
cp sites.json.example sites.json     # edit your domain + competitors
export ANTHROPIC_API_KEY="sk-ant-..."
avm --no-wizard
```

## What you get

Output goes to `data/citations-{timestamp}.json`. Schema:

```json
{
  "run_date_utc": "2026-04-30",
  "generator": "citation_check.py",
  "version": "1.0",
  "target_domain": "your-domain.com",
  "model": "claude-sonnet-4-6",
  "runs_per_query": 2,
  "summary": {
    "queries_total": 5,
    "queries_cited": 1,
    "queries_uncited": 4
  },
  "queries": [
    {
      "query": "best fractional Head of AI for mid-market construction",
      "runs": 2,
      "cited": false,
      "citation_rate": 0.0,
      "position_mode": null,
      "position_min": null,
      "position_max": null,
      "citations_union": [
        {
          "url": "https://competitor-a.com/category-page",
          "title": "Competitor A category page",
          "domain": "competitor-a.com"
        }
      ]
    }
  ]
}
```

Each query runs N times (default 2) so the data is averaged across runs, not a single sample. `position_mode` reports where your domain ranks in the citation list across runs. `citations_union` is the union of every URL Claude cited across all runs of that query.

Pipe the JSON into a spreadsheet, a dashboard, a Slack notification, whatever you already use. The JSON is the deliverable.

See [`sample-data/citations-example.json`](sample-data/citations-example.json) for a real anonymized run.

## Prospect audit (`avm audit-prospect`)

Score any public domain 0-100 across six AI visibility categories. Built for quick discovery calls: run it in under 90 seconds, show the result, explain the gaps.

```bash
avm audit-prospect https://example.com
avm audit-prospect https://example.com --json   # pipe into Slack or a spreadsheet
```

Sample output:

```
╭──── AI Visibility Readiness Audit · work-smart.ai ────────────╮
│                                                               │
│  Score: 95 / 100  ·  Grade: A                                 │
│  Sampled: 10 pages from sitemap  ·  6.0s                      │
│                                                               │
│  Crawler Accessibility    30 / 30  ✓                          │
│  Discovery Files          15 / 15  ✓                          │
│  Schema Markup            10 / 15                             │
│  Render Performance       15 / 15  ✓                          │
│  Meta + HTML Quality      10 / 10  ✓                          │
│  Open Graph + Social      10 / 10  ✓                          │
│                                                               │
│  Top 3 fixes by impact:                                       │
│  1. Add Service schema to service pages (+5 pts, ~1h)         │
│                                                               │
╰───────────────────────────────────────────────────────────────╯
```

**Scoring rubric (100 points total):**

| Category | Points | What it checks |
|---|---|---|
| Crawler Accessibility | 30 | robots.txt access for 20 AI bot UAs (GPTBot, ClaudeBot, PerplexityBot, and 17 others) |
| Discovery Files | 15 | llms.txt present, sitemap fresh (< 30 days), robots.txt explicitly names AI bots |
| Schema Markup | 20 | JSON-LD blocks: Service, FAQPage (5+ Q&As), Article on blog posts, BreadcrumbList |
| Render Performance | 15 | Pages return 200 with Googlebot UA, content is pre-rendered or large |
| Meta + HTML Quality | 10 | Title 30-65 chars, description 120-160 chars, single H1, canonical matches URL |
| Open Graph + Social | 10 | og:title, og:description, og:image (reachable), og:type, twitter:card |

**Grade thresholds:** A (90+), B (80+), C (70+), D (60+), F (below 60)

The audit fetches pages with a GPTBot UA so pre-render layers serve full HTML, matching what AI crawlers actually receive.

No API keys required. No writes. Reads only.

## Adjacent query discovery (`--expand`)

Your 5 base queries are probably the most obvious ones. Your competitors have spent months building authority on them.

Run `avm --expand` and the tool generates 15 adjacent queries by varying specificity, intent, and vocabulary. It runs a full citation check on all 20, then ranks the expanded queries by **winnability** — citation density, surface softness, your partial visibility.

```bash
avm --expand
```

Output adds a **RECOMMENDED TARGETS** panel showing the 5 expanded queries you can realistically break into in 30-60 days, with per-query rationale:

```
  1. fractional ai lead for smb
     Winnability: 50%  ·  soft surface mix (forums/blogs dominate); already cited by Perplexity

  2. best ai tools for wealth advisors
     Winnability: 7%  ·  soft surface mix (forums/blogs dominate)
```

The JSON output adds `expanded_queries` (same schema as `queries`) and `recommended_targets` (query + winnability_score + rationale).

Cost: ~$0.90 per `--expand` run on the default Haiku model (15 extra queries × 3 engines × 2 runs = 90 calls).

## Source-surface categorization

Every cited URL is automatically categorized by surface type. v0.2.2 added 10 distinct community sub-categories replacing the coarse "forum" bucket:

| Category | Examples |
|---|---|
| `reddit` | reddit.com |
| `quora` | quora.com |
| `stackoverflow` | stackoverflow.com |
| `stackexchange` | *.stackexchange.com |
| `ycombinator` | news.ycombinator.com |
| `g2` | g2.com |
| `trustpilot` | trustpilot.com |
| `producthunt` | producthunt.com |
| `press` | techcrunch.com, forbes.com, ... |
| `blog` | medium.com, substack.com, ... |
| `consulting_competitors` | headofai.ai, chiefaiofficer.com, ... |
| `industry_news` | prnewswire.com, constructiondive.com, ... |

Categories roll up to parent buckets (`community`, `press`, `official`, `blog`, `social`) for top-level analysis and baseline comparisons.

The per-query breakdown shows the surface mix and a suggested action:

```
Surface mix: 40% press · 30% reddit · 20% blog · 10% uncategorized
Action: engage in relevant subreddits — comment under your own account
```

**Override with `surfaces.json`** in your working directory to add your own categories:

```json
{
  "press": ["constructiondive.com"],
  "industry_news": ["wealthmanagement.com", "finews.com"]
}
```

## Community threads (`avm threads`)

Read all historical citation data and surface the specific Reddit, Quora, and other community threads that keep being cited across multiple queries and engines. These are the threads worth engaging with under your own account.

```bash
avm threads                    # All community surfaces, min 1 query
avm threads --surface reddit   # Reddit only
avm threads --min-queries 2    # Only threads cited across 2+ distinct queries
avm threads --top 10           # Top 10 only
avm threads --json             # Machine-readable output
```

Output:

```
╭──── HIGH-LEVERAGE COMMUNITY THREADS ──────────────────────╮
│                                                           │
│  1. reddit.com/r/consulting/comments/abc123               │
│     Surface: reddit  ·  Cited by: Perplexity, ChatGPT     │
│     Across: fractional head of ai                         │
│                                                           │
│  2. quora.com/What-is-a-fractional-head-of-AI             │
│     Surface: quora  ·  Cited by: ChatGPT, Claude          │
│     Across: what is fractional head of ai                 │
│                                                           │
│  Action: comment on these threads from your own account.  │
│  Do NOT use a posting service. Comments must come from    │
│  a real account that builds karma over time.              │
│                                                           │
╰───────────────────────────────────────────────────────────╯
```

The command is useful once you have 2+ historical runs. With one run it shows threads cited in at least 1 query.

## Vertical baselines

AVM ships with built-in surface-share baselines per engine per industry vertical, so you know whether your surface mix is above or below average for your category.

```bash
avm --vertical professional_services   # Use professional services baselines
avm --vertical construction            # Use construction baselines
avm --vertical wealth_management       # Use wealth management baselines
```

You can also add a `"vertical"` field to your `sites.json` entry and it will be picked up automatically:

```json
[
  {
    "name": "Your Brand",
    "url": "https://your-domain.com",
    "owner": "self",
    "vertical": "professional_services"
  }
]
```

When a vertical is active, each query's surface mix shows a baseline comparison:

```
Surface mix: 60% community · 25% press · 15% blog
  community: 60%  (baseline ~18%, significantly above average)
  press:     25%  (baseline 25%, at baseline)
```

**Baseline data source:** Tinuiti Q1 2026 AI Citation Trends Report + 5W AI Platform Citation Source Index (May 2026). Perplexity default: 24% community. ChatGPT: ~5% community. Claude: ~5% (estimated — no public data). Vertical breakdowns (construction, legal, wealth_management) are estimated from B2B category research; treat as directional, not hard data. Updated quarterly with each minor release.

Available verticals: `default`, `professional_services`, `construction`, `legal`, `wealth_management`, `distribution`.

## Citation trajectory (`avm trend`)

Run `avm trend` to see your citation rate over time across all historical runs in `data/`. No new API calls — pure historical analysis.

```bash
avm trend                         # Full trajectory across all runs
avm trend --query "fractional"    # Filter to queries matching a substring
avm trend --since 2026-01-01      # Runs on or after a specific date
avm trend --engine perplexity     # Filter to one engine
avm trend --json                  # Raw JSON output
```

Output:

```
╭──── CITATION TRAJECTORY · work-smart.ai ──────────────────╮
│                                                           │
│  2026-04-25  ▏      0 of 5 cited                          │
│  2026-05-01  ▏█     1 of 5 cited  ↑ +1                    │
│  2026-05-08  ▏██    2 of 5 cited  ↑ +1                    │
│                                                           │
│  Trajectory: improving (+2 in 3 runs)                    │
│                                                           │
│  New competitors appearing:                               │
│    + headofai.ai  (since run 2)                           │
│                                                           │
╰───────────────────────────────────────────────────────────╯
```

Each run of `avm` writes to `data/citations-{date}.json`. The trend command reads all those files chronologically. Run weekly, you'll see your trajectory build up automatically.

## How it works

Four small scripts. Each runs independently. Each writes JSON.

```
ai-visibility-monitor/
├── citation_check.py    Runs each query through Claude with web_search on.
│                        Records every URL in the response. Flags whether
│                        your domain appeared.
├── gsc_pull.py          Pulls Google Search Console data: top queries,
│                        striking-distance positions (5 to 20).
├── ga4_pull.py          Pulls GA4 with an AI-referrer slice (chatgpt.com,
│                        claude.ai, perplexity.ai, gemini.google.com).
├── prereqs_sweep.py     Audits robots.txt, llms.txt, and sitemap for
│                        AI bot crawlability.
└── data/                JSON output for every run, committed for transparency.
```

Four small scripts, single language (Python 3.10+), no framework dependencies beyond the Anthropic SDK and Google API client. Auditable in an afternoon.

## Configuration

Two files, both human-readable.

**queries.md** — your 5 buyer queries, one per line:

```
best fractional Head of AI for mid-market construction
how to track AI search visibility
generative engine optimization tools 2026
AI consulting Miami
fractional CTO vs fractional Head of AI
```

**sites.json** — your domain and competitors as an array:

```json
[
  {
    "name": "Your Brand",
    "url": "https://your-domain.com",
    "owner": "self"
  },
  {
    "name": "Competitor A",
    "url": "https://competitor-a.com",
    "owner": "competitor"
  }
]
```

The site with `"owner": "self"` is treated as your domain. All others are tracked as competitors.

## Authentication

The wizard will prompt for these on first run and save them to `.env`. If you prefer, you can set them as environment variables manually.

| Use case | Credential needed | Cost |
|---|---|---|
| Citation check (Claude engine) | `ANTHROPIC_API_KEY` | ~$0.30 per run on default Haiku 4.5 |
| Citation check (ChatGPT engine) | `OPENAI_API_KEY` | ~$0.10 per run on gpt-4o-mini |
| Citation check (Perplexity engine) | `PERPLEXITY_API_KEY` | ~$0.10 per run on Sonar (free tier available) |
| GSC + GA4 pulls | Google ADC | Free |
| Prereqs sweep | None (HTTP only) | Free |

Missing keys = engine skipped with warning. The tool runs fine with just one of the three engines if that's all you have.

**Anthropic** (required for default behavior):

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Get a key at [console.anthropic.com](https://console.anthropic.com).

**OpenAI** (optional, for ChatGPT engine):

```bash
export OPENAI_API_KEY="sk-..."
```

Get a key at [platform.openai.com/api-keys](https://platform.openai.com/api-keys).

**Perplexity** (optional, for Perplexity engine):

```bash
export PERPLEXITY_API_KEY="pplx-..."
```

Get a key at [perplexity.ai/account/api](https://perplexity.ai/account/api).

**Google APIs** (optional, for `avm gsc` and `avm ga4`):

```bash
gcloud auth application-default login
```

Requires the Google Cloud SDK installed locally. See [Google ADC docs](https://cloud.google.com/docs/authentication/application-default-credentials) if you haven't set this up before.

## Choosing a model

Default is `claude-haiku-4-5-20251001` for cost efficiency. For most queries (specific, branded, location-tagged) the citation results match the more expensive Sonnet 4.6 within ~80% overlap.

For broad or abstract category queries (e.g., "ai consultant for family offices"), citation variance is higher and you may want to opt up:

```bash
avm --model claude-sonnet-4-6
```

That costs ~10x more per run (~$3 vs $0.30). Worth it for important deep-dive analyses, overkill for routine weekly checks.

## How this compares

### Versus paid SaaS

| Tool | Price (monthly) | Vendor-managed | Local credentials | Open source |
|---|---|---|---|---|
| **AI Visibility Monitor** | **~$0.30/run, ~$1-2/month for weekly runs** | No | Yes | Yes |
| [Otterly.AI](https://otterly.ai) | $29 | Yes | No | No |
| [Trakkr.ai](https://trakkr.ai) | Free beta | Yes | No | No |
| [GenRank](https://genrank.io) | Pricing on request | Yes | No | No |
| SEMrush AI Visibility | $99 | Yes | No | No |
| [Profound](https://tryprofound.com) | $499 (Lite) | Yes | No | No |

The paid tools have nicer dashboards. This tool has a JSON output you can pipe into your own systems, runs on your own credentials, and the cost floor is roughly the price of one cup of coffee per year (weekly runs).

### Versus other open-source projects

| Project | Surface | Output | Cost |
|---|---|---|---|
| **AI Visibility Monitor** | **CLI, 4 Python scripts** | **JSON** | **$1 to $3/mo (Anthropic API)** |
| [GEO/AEO Tracker](https://github.com/danishashko/geo-aeo-tracker) | Next.js dashboard | UI + IndexedDB | Free + Bright Data API (paid) |
| [AI Product Bench](https://github.com/amplifying-ai/ai-product-bench) | Research benchmark | JSONL + HTML dashboard | Varies by model |
| [AI Monitor](https://getaimonitor.com/) | Hosted brand-tracking tool | UI dashboard | Free + hosted version |
| [AutoGEO](https://github.com/cxcscmu/AutoGEO) | Content rewriter, different category | Rewritten copy | Varies |

GEO/AEO Tracker is the deployable dashboard. AI Product Bench is the consistency-research benchmark. AI Monitor is the hosted alternative. AVM is the CLI you wire into your own systems. Different audiences. Use whichever maps to what you're actually trying to build.

## Roadmap

Public, structured, every commitment visible.

### v0.1.1 (shipped)

- 🟢 [#1 Pretty-print citation_check output (rich library)](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/1)
- 🟢 [#2 Add `--interactive` flag for first-time setup](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/2)

### v0.2.0 (shipped)

- 🟢 [#3 Multi-model rotation: Claude + ChatGPT + Perplexity](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/3)
- 🟢 [#11 Single `avm` command with subcommands](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/11)
- 🟢 [#12 Auto-install missing dependencies](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/12)
- 🟢 [#13 First-run setup wizard](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/13)
- 🟢 [#14 Switch default model to Haiku 4.5 (~10x cheaper)](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/14)
- 🟢 [#15 Progress output to stderr for clean --json pipe](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/15)

### v0.2.1 (shipped)

- 🟢 [#16 Adjacent query discovery (`--expand`)](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/16)
- 🟢 [#17 Source-surface categorization](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/17)
- 🟢 [#18 `avm trend` citation trajectory command](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/18)

### v0.2.2 (shipped)

- 🟢 [#19 Fix scoring + expand surface categories + tighten expansion prompt](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/19)
  - Winnability scoring now produces spread across queries (weighted additive formula)
  - Rationale is specific: references top citing domain, surface %, per-engine visibility
  - Expansion prompt is ICP-constrained (infers buyer profile from base queries)
  - 10 distinct community sub-categories: reddit, quora, stackoverflow, stackexchange, ycombinator, g2, trustpilot, yelp, glassdoor, producthunt
  - `community` parent bucket for rollup reporting
  - `consulting_competitors` and `industry_news` categories for AI consulting use case
  - `avm threads` subcommand: surface high-leverage community threads from citation history
  - Vertical baselines: built-in surface-share benchmarks per engine per industry vertical (`baselines.json`)
  - `--vertical` flag for baseline annotations in surface mix output

### v0.2.x backlog

- ⚪ [#4 Per-bot user-agent crawl coverage tests](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/4)
- ⚪ [#5 Bing Webmaster Tools data pull (feature flag)](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/5)
- ⚪ [#6 IndexNow ping script](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/6)
- ⚪ [#8 Visibility score (0-100 composite metric)](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/8)
- ⚪ [#9 GitHub Actions workflow for scheduled runs](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/9)
- ⚪ [#10 Top-cited competitors aggregation across queries](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/10)

🟢 shipped · 🟡 in progress · ⚪ planned

Full milestone view: [v0.1.1](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/milestone/1) · [v0.2.0](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/milestone/2) · [v0.2.1](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/milestone/3) · [v0.2.2](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/milestone/4)

## Contributing

PRs, issues, and design feedback welcome. The roadmap above is shaped by user feedback. Most of v0.2.0 came from a single Reddit comment.

If you run the tool on your own domain and the output surfaces something useful or surprising, open an issue and tell me what you found. The data shapes the next release.

## Security

Found a security issue? Email ignacio@work-smart.ai instead of opening a public issue. Responsible disclosure appreciated.

## License

MIT, see [LICENSE](LICENSE). Yours to fork, modify, and use commercially. No lock-in, no attribution required (though appreciated).

## Built by

[![Work-Smart.ai](https://img.shields.io/badge/Built_by-WORK--SMART.AI-B08D3E?style=for-the-badge)](https://work-smart.ai)

[Work-Smart.ai](https://work-smart.ai) is a fractional Head of AI practice for mid-market companies in Miami and LatAm. Operated by [Ignacio Lopez](https://www.linkedin.com/in/ignaciolopez), bilingual English and Spanish, specializing in mid-market AI implementations: WhatsApp agents, document AI, AI visibility, custom copilots.

If your team is running into 0 of 5 citations on your buyer queries and wants help moving the number, that's the day job. [Get in touch](https://work-smart.ai/contact).
