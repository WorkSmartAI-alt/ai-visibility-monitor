# Roadmap

AI Visibility Monitor is in active development. This file tracks what's shipped, what's in flight, and what's next.

Tracking is also visible via [GitHub Milestones](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/milestones) and [open Issues](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues).

## Shipped

### v0.1.0 — April 25, 2026
Initial release.
- `citation_check.py` — runs Claude with web_search against 5 user-defined buyer queries, records every URL Claude cites, flags whether your domain shows up
- `gsc_pull.py` — Google Search Console data, top queries, striking-distance keywords (positions 5-20)
- `ga4_pull.py` — GA4 data with AI-referrer slice (chatgpt.com, claude.ai, perplexity.ai, gemini.google.com)
- `prereqs_sweep.py` — checks robots.txt + llms.txt + sitemap for AI bot crawlability

## In flight

### v0.1.1 — UX patches (target: this week)
Bundled patch release with two improvements based on first-week user feedback. Tracking issues: [#1](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/1), [#2](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/2).

- **Pretty-print output** (rich library): default output becomes an ASCII-boxed summary with colored fields. Raw JSON preserved via `--json` flag for scripting and CI.
- **Interactive CLI** (`--interactive` flag): prompts for 5 buyer queries on the terminal instead of requiring `queries.md` edits. `queries.md` remains the canonical config; interactive is a setup helper.

### v0.2.0 — Multi-model support (target: next week)
Rotate citation checks across Claude, ChatGPT, and Perplexity. Each model surfaces different competitor patterns — treat them as separate channels, not redundant samples. Lower cadence per model to keep API cost sane. Tracking issue: [#3](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/3).

## Backlog (v0.2.x and beyond)

Not yet committed to a specific version. Open for community input via the issue tracker.

- **Per-bot user-agent testing in `prereqs_sweep.py`** ([#4](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/4)): test crawlability with GPTBot, ClaudeBot, PerplexityBot, Google-Extended, and Bingbot to surface mismatches.
- **Bing Webmaster Tools data pull behind a feature flag** ([#5](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/5)): optional Bing data, default off.
- **IndexNow ping script** ([#6](https://github.com/WorkSmartAI-alt/ai-visibility-monitor/issues/6)): bundled IndexNow submission for fast Bing indexing (which feeds ChatGPT search and Microsoft Copilot).

## How to contribute

- Pick an issue from the tracker, comment to claim it, send a PR
- File a new issue if you have a use case or pattern that isn't covered
- Star the repo if you find it useful — that's the signal that drives prioritization

## Versioning

Semantic versioning. Patch releases (v0.1.1, v0.1.2) are backward-compatible UX or bug fixes. Minor releases (v0.2.0, v0.3.0) add new capabilities. Major release (v1.0.0) will land when the core surface is stable enough to commit to long-term API compatibility.
