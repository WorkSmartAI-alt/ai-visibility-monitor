# Contributing

Issues and PRs welcome.

## What's especially useful

- A `psi_pull.py` for Core Web Vitals via the PageSpeed Insights API (no auth needed). Same JSON output pattern as the existing scripts.
- Bing Webmaster Tools support alongside GSC. Bing's share of AI engine training data is non-trivial.
- A `--start` and `--end` flag on `gsc_pull.py` for explicit window comparison (pre-redeploy vs post, etc.).
- Postgres or DuckDB output mode as an alternative to JSON files, for users with longer history.
- Per-bot user-agent testing in `prereqs_sweep.py` (currently uses one generic UA, doesn't catch bot-specific divergences).
- A `brand_mentions.py` extension to `citation_check.py` that scans the answer text (not just the citation URLs) for mentions of your brand without a link.

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
