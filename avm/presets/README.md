# AVM Presets

Presets are curated query sets packaged with AVM. Each preset is a YAML file
that defines a named set of buyer queries, their tiers, and the target pages
they map to.

## Using a preset

```bash
avm --preset work-smart-mid-market
avm --preset work-smart-mid-market --expand
avm audit-prospect --preset work-smart-mid-market https://example.com
avm presets list
avm presets show work-smart-mid-market
```

## Bundled presets

| Preset | Queries | ICP |
|---|---|---|
| work-smart-mid-market | 21 | Mid-market AI consulting buyers (universal + industry-specific) |

## Contributing a preset

1. Copy the schema below into a new file named `<slug>.yaml`.
2. Add your queries. Each query needs `id`, `text`, `tier`, and `target_page`.
3. Run `avm presets list` to verify it appears.
4. Open a PR. The PR description should explain the ICP and how the queries were sourced.

## Schema

```yaml
name: your-preset-name
slug: your-preset-name          # must match filename without extension
description: >
  One paragraph describing the ICP and intended use.
version: "1.0"
last_updated: "2026-01-01"
maintainer: Your Name or Organization
source_url: https://optional-methodology-url.com
license: MIT

queries:
  - id: Q01
    text: "Exact buyer phrasing"
    tier: alpha                 # alpha, beta, gamma, s_tier, or a custom label
    subtier: Category name      # optional grouping label
    target_page: /your/page    # the page on the audited domain this query maps to
```

## Tier conventions (Work-Smart schema)

The `work-smart-mid-market` preset uses four tiers. Other presets can define
their own tier names as long as they are consistent within the file.

| Tier | Meaning in Work-Smart schema |
|---|---|
| alpha | Highest commercial intent, broadest buyer base |
| beta | Objection handlers and use-case anchors |
| gamma | Industry-specific, narrow ICP |
| s_tier | Solopreneur / individual practitioner entry point |
