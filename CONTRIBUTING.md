# Contributing

Issues and PRs welcome.

## What's especially useful

- A `psi_pull.py` for Core Web Vitals via the PageSpeed Insights API (no auth needed). Same JSON output pattern as the existing scripts.
- Bing Webmaster Tools support alongside GSC. Bing's share of AI engine training data is non-trivial.
- A `--start` and `--end` flag on `gsc_pull.py` for explicit window comparison (pre-redeploy vs post, etc.).
- Postgres or DuckDB output mode as an alternative to JSON files, for users with longer history.
- Per-bot user-agent testing in `prereqs_sweep.py` (currently uses one generic UA, doesn't catch bot-specific divergences).
- A `brand_mentions.py` extension to `citation_check.py` that scans the answer text (not just the citation URLs) for mentions of your brand without a link.

## Contributing a preset

Presets are the easiest contribution path. A preset is a YAML file in
`avm/presets/` that bundles a curated query set for a specific buyer ICP.

**To add a preset:**

1. Copy the schema from `avm/presets/README.md`.
2. Name the file `<slug>.yaml` (e.g. `law-firm-mid-market.yaml`).
3. Add at minimum 10 queries, each with `id`, `text`, `tier`, and `target_page`.
4. Run `avm presets list` to confirm it appears.
5. Run `avm --preset <slug> --dry-run` to verify all queries load.
6. Open a PR. Include: the ICP the preset targets, how the queries were sourced
   (buyer interviews, keyword research, transcript corpus), and a sample run
   showing the tool actually runs against a relevant domain.

**Preset quality bar:** queries must be in buyer-frame phrasing ("How do I..."
not "best AI tool for..."). Each query should map to a real page on the target
domain (`target_page`) that answers it. Generic keyword-research phrasing that
no buyer would actually type into ChatGPT will be asked to revise.

**Planned presets (open to contributors):**
- `law-firm-mid-market` (8-12 queries, legal industry ICP)
- `wealth-management-ria` (8-12 queries, RIA / family office ICP)
- `construction-general-contractor` (8-12 queries, construction ICP)
- `b2b-saas-early-stage` (cross-vertical, SMB SaaS buyer)

## How to submit

1. Open an issue first if it's a substantial change. A 30-second back-and-forth on scope saves an hour of rework.
2. Fork, branch, PR.
3. Keep the scripts dependency-light. Each script should run with stdlib + at most one official Google or Anthropic SDK.
4. JSON output schema is the contract. If you change a key or shape, document it in the PR description.
5. No external dashboard frameworks, no SaaS dependencies, no telemetry.

## Style

- Python 3.10+ (the type hints assume this).
- Standard library first. Add a dep only when necessary.
- Keep CLI flags consistent across scripts (`--days`, `--output-dir`, `--dry-run`).
- Print a useful terminal summary at the end of each run, the kind a human glances at and gets value from.

## License

Contributions are licensed under MIT, the same as the rest of the repo.
