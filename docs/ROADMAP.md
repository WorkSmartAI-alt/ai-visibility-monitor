## v0.3.1 — Deterministic sampling

The audit-prospect sitemap sampler currently uses random selection of 10 URLs, which produces 1-point score variance across consecutive runs on the same domain (verified May 10 2026: work-smart.ai scored 99/100/100/99/100 across 5 consecutive runs).

Fix: replace random sampling with deterministic selection. Options:
- Top 10 URLs by sitemap order (simplest, but biases toward static pages)
- Top 10 URLs by lastmod date (recency-weighted)
- Seeded random with the domain as seed (reproducible per domain)

Recommended: option 3 (seeded random by domain) for fairness across page types. Run 5x consecutive on work-smart.ai post-fix to confirm 0-point variance.
