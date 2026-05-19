# subconscious-mcp validation results

**Project:** subconscious-mcp v0.1.0
**Date:** 2026-05-19
**Author:** Vishal Jayaprakash
**Repository:** https://github.com/vishaltorc/subconscious-mcp

---

## Summary

subconscious-mcp v0.1.0 was validated on a 150-task paraphrase experiment using the official MCP Python SDK over stdio. The MCP server worked end to end. Two threshold settings were tested: 0.9 (conservative) and 0.8 (aggressive). Production token savings were 30.6% and 67.1% respectively, with cache accuracies of 98.1% and 95.0%. The experiment surfaced a novel failure mode, here called **first-fill semantic drift**, where the first paraphrase to populate a query family determines the cached answer for all subsequent semantically-similar queries, propagating any interpretation error from that first answer to the entire family.

| Threshold | Hit rate | Cache accuracy | Production token savings |
|---|---|---|---|
| 0.9 | 36.0% (54/150) | 98.1% (53/54) | 30.6% |
| 0.8 | 67.3% (101/150) | 95.0% (96/101) | 67.1% |

The architecture works. The dominant tuning parameter is the similarity threshold. The bottleneck is the embedding model, not the system design.

---

## Methodology

30 hand-written seed tasks across six categories (arithmetic, factual recall, classification, simple reasoning, text rewriting, structured data extraction). Each seed paraphrased four times by claude-haiku-4-5. 150 tasks total, shuffled with random.seed(42). Three phases per run: variant generation, cached experiment with System 1 / System 2 routing and an independent judge on each cache hit, baseline phase with cache disabled.

Infrastructure: subconscious-mcp v0.1.0 over stdio, ChromaDB cosine space, sentence-transformers all-MiniLM-L6-v2 (384-dim local), claude-haiku-4-5 for both task and judge calls.

Paraphrase generation was not temperature-pinned, so the 120 paraphrases differ between the two runs. The 30 seeds are identical across runs.

---

## Run 1: Threshold 0.9

| Metric | Value |
|---|---|
| Tasks | 150 |
| System 1 hits | 54 (36.0%) |
| System 2 misses | 96 |
| Cache accuracy (judge verified) | 53 / 54 = 98.1% |
| Tokens with cache | 11,420 |
| Baseline tokens | 16,456 |
| Judge overhead | 7,716 |
| Production token savings | 30.6% |

The single "wrong" cache hit: similarity 0.9272, task "What do you get when you multiply 24 by 17?", cached answer "17 multiplied by 24 is 408." Arithmetically correct. The judge flagged operand-order reversal, not the result. This is a judge error, not a cache error. True cache accuracy is plausibly 54 / 54.

---

## Run 2: Threshold 0.8

| Metric | Value |
|---|---|
| Tasks | 150 |
| System 1 hits | 101 (67.3%) |
| System 2 misses | 49 |
| Cache accuracy (judge verified) | 96 / 101 = 95.0% |
| Tokens with cache | 5,480 |
| Baseline tokens | 16,669 |
| Judge overhead | 15,085 |
| Production token savings | 67.1% |

Five wrong cache hits: 1 judge error (the same 17 x 24 case), 4 genuine semantic errors all returning the same cached answer for a "numbers vs digits" extraction family. See next section.

---

## The first-fill semantic drift finding

Four real semantic errors at threshold 0.8 returned the same cached answer:

> "Digits found: 3, 1, 2, 2. Or as a set of unique digits: 1, 2, 3."

This was correct for one paraphrase, "Pull out all digits...", which landed first in the run. The answer became the cached value for the entire family. Four later variants asked for **numbers** (3, 12, 2 in the milk-and-eggs sentence), hit this entry at similarities 0.82 to 0.94, and received the digits answer (1, 2, 3) which is wrong for "extract all numbers".

We name this **first-fill semantic drift**: in a cache that fills bottom-up, the first cached answer for a family of semantically-similar queries propagates to all later queries above the similarity threshold, even when those queries carry a subtly different interpretation.

Threshold 0.9 ran clean because the lower-quality interpretive paraphrases scored below 0.9 and were routed to System 2. This failure mode is not described in published cache research because most cache work tests identical-input retrieval. We surfaced it via paraphrased retrieval at 150-task scale.

Mitigations (v0.2): multi-answer per cluster, interpretive sensitivity probes, operator review of first-fill entries. None are in v0.1.

---

## Cost framing: research overhead vs production cost

The token savings numbers exclude judge calls. The judge is a research-time evaluation tool, not a production component. In production, trust in the cache is established empirically and through periodic sampling, not per-call verification.

If judge cost is included, both runs spend more than baseline:

| | Cache + judge | Baseline | Net |
|---|---|---|---|
| Threshold 0.9 | 19,136 | 16,456 | -16.3% |
| Threshold 0.8 | 20,565 | 16,669 | -23.4% |

This is not how the system operates in production. Reported transparently so readers can do the math.

---

## Threshold recommendations

| Threshold | Behavior | Recommended for |
|---|---|---|
| 0.95 | Almost no hits, near-perfect accuracy | High-stakes outputs |
| 0.90 | ~36% hit rate, 98% accuracy, ~30% savings | Safety-conscious applications |
| 0.85 | ~55-60% hit rate, ~96-97% accuracy, ~55% savings | Default. Balanced |
| 0.80 | ~67% hit rate, 95% accuracy, ~67% savings | Cost-sensitive applications |
| 0.70 | ~79% hit rate, unmeasured accuracy | Not recommended without validation |

subconscious-mcp v0.1.0 ships with default_threshold = 0.85.

---

## Known limitations

1. Single embedding model tested (all-MiniLM-L6-v2)
2. Synthetic paraphrases, not real agent traces
3. Judge from same model family as task LLM (Haiku)
4. Small scale (150 tasks)
5. Single task LLM (Haiku only)
6. Paraphrase regeneration confound between runs
7. First-fill drift mitigations deferred to v0.2

---

## What this validates

- subconscious-mcp v0.1.0 operates correctly as an MCP stdio server
- The four MCP tools function end to end
- Semantic caching at sentence-embedding level produces real token savings on paraphrased queries
- 95% to 98% cache accuracy is achievable at sensible thresholds
- The architecture is sound at 150-task scale

## What this does not validate

- Production-scale (10,000+ task) behavior
- Real agent trace usage patterns
- Generalization across task types not in the seed set
- Cross-model behavior
- Concurrent access
- Long-running TTL and invalidation behavior

---

## Files in this directory

| File | Description |
|---|---|
| results.md | This document |
| results_threshold_0.9.csv | Per-task data, 0.9 run |
| results_threshold_0.8.csv | Per-task data, 0.8 run |
| tokens_per_task_threshold_0.9.png | Token chart, 0.9 |
| tokens_per_task_threshold_0.8.png | Token chart, 0.8 |
| threshold_tradeoffs.png | Post-hoc threshold sweep |
| logs/run_threshold_0.9.log | Filtered run log, 0.9 |
| logs/run_threshold_0.8.log | Filtered run log, 0.8 |

The experiment harness lives in a separate private repository. Available on request.

---

## Citation

> Jayaprakash, V. (2026). subconscious-mcp: A learning memory layer for MCP agents. https://github.com/vishaltorc/subconscious-mcp

---

*Validation run on 2026-05-19. subconscious-mcp v0.1.0.*
