# Model comparison: Haiku 4.5 vs Sonnet 4.6

**Date:** 2026-05-01  
**Purpose:** Validate that `claude-haiku-4-5-20251001` produces equivalent citation results to `claude-sonnet-4-6` before making Haiku the default model in v0.2.0.  
**Protocol:** 5 queries × 2 runs each through both models. Compute top-3 cited domain overlap per query. Threshold: 80% average overlap required to default Haiku.

---

## Protocol

```bash
# Sonnet baseline
avm --model claude-sonnet-4-6 --runs 2

# Haiku comparison
avm --model claude-haiku-4-5-20251001 --runs 2

# Compute overlap of top-3 cited domains per query
# If average overlap >= 80%: default Haiku
# If average overlap < 80%: keep Sonnet default, document Haiku as opt-in
```

Calls run sequentially with 5-second sleep between each to stay under rate limits.

---

## Queries tested

1. fractional head of ai for mid-market companies
2. fractional head of ai miami
3. ai consultant for family offices and wealth management
4. claude cowork training and custom skills creation
5. ai visibility monitor open source citation tracker

Target domain: `work-smart.ai`

---

## Results

| Query | Sonnet top-3 | Haiku top-3 | Overlap |
|---|---|---|---|
| Q1: fractional head of ai for mid-market | headofai.ai, medium.com, prnewswire.com | headofai.ai, medium.com, prnewswire.com | **100%** |
| Q2: fractional head of ai miami | fastdatascience.com, headofai.ai, jobleads.com | fastdatascience.com, headofai.ai, jobleads.com | **100%** |
| Q3: ai consultant for family offices | familywealthreport.com, pwc.com, wealthsolutionsreport.com | eton-solutions.com, fintrx.com, masttro.com | **0%** |
| Q4: claude cowork training and skills | anthropic.skilljar.com, findskill.ai, support.claude.com | anthropic.skilljar.com, findskill.ai, support.claude.com | **100%** |
| Q5: ai visibility monitor citation tracker | brightdata.com, github.com, therankmasters.com | brightdata.com, github.com, therankmasters.com | **100%** |

**Average overlap: 80.0%**

---

## Analysis

4 of 5 queries produced identical top-3 results between Haiku and Sonnet. The divergent query (Q3, "ai consultant for family offices and wealth management") is notably broad — the category has more content diversity, so variance between runs and models is expected.

Sonnet run times: ~22–28 seconds per call  
Haiku run times: ~5–8 seconds per call  
**Haiku is ~4x faster per call.**

Estimated cost per 5-query × 2-run session:
- Sonnet 4.6: ~$1.50–3.00
- Haiku 4.5: ~$0.10–0.30

---

## Decision

**Average overlap = 80.0% ≥ 80% threshold → Default Haiku confirmed.**

`claude-haiku-4-5-20251001` is the v0.2.0 default. Use `--model claude-sonnet-4-6` to opt up to Sonnet for higher fidelity on broad/ambiguous queries like Q3.

---

## Re-running this comparison

To validate a future model swap, run the same protocol:

```bash
python3 tests/run_comparison.py \
  --model-a claude-sonnet-4-6 \
  --model-b claude-haiku-4-5-20251001 \
  --runs 2
```

(Script to be added in v0.2.1.)
