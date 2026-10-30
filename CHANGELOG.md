# Changelog

## v0.2.3 (2026-10-30)

- Default Claude model is now `claude-haiku-5-5` (was `claude-haiku-4-5-20251001`). Haiku 4.5 reached its earliest retirement window on 2026-10-15 per Anthropic's deprecation page; moving now avoids a silent break later.
- `--model` help text and README examples now point to `claude-sonnet-5-5` for the higher-fidelity option.
- README "Choosing a model" section rewritten: the Haiku vs Sonnet agreement figure came from 4.x models and is marked as not yet re-measured on 5.5.
- Web search stays on `web_search_20250305`, the basic tool version that works on every Claude model and platform.
- No change to the ChatGPT (`gpt-4o-mini`) or Perplexity (`sonar`) engine defaults.

## v0.2.2 (2026-05-01)

- Community surface intelligence and scoring fixes.

## v0.2.1 (2026-05-01)

- Adjacent query discovery, `avm trend` command, source-surface categorization.

## v0.2.0

- Multi-engine citation checks across Claude, ChatGPT and Perplexity.
