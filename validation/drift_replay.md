# Drift replay: running the v0.2.0 detector on the v0.1.0 validation run

**Script:** `validation/replay_drift.py`
**Data:** `validation/results_threshold_0.8.csv` (150 tasks, 101 cache hits, threshold 0.8)
**Detector:** `Memory.drift_report(min_hits=3, min_spread=...)`, v0.2.0
**Date:** 2026-06-10

## Question

The threshold-0.8 validation run contained exactly one genuine first-fill
semantic drift family: the "digits vs numbers" entry, where the cached answer
for "Pull out all digits..." served four later paraphrases asking for
numbers (task ids 25 seed; 29, 107, 118, 135 propagation; documented in
`results.md`). At the time, the only way to find it was an LLM judge call on
every cache hit.

Can `drift_report`, which uses only echo-log geometry (zero extra LLM or
embedding calls), find the same family?

## Method

The v0.1.0 run predates the echo log, so the replay reconstructs it:

1. Group the 101 cache-hit rows (`system_used == "S1"`) by their
   `cached_answer` string: hits that returned the same answer were served by
   the same stored entry. This yields 32 families.
2. For each family, the stored task is the first `S2` row (file order) with
   the same `cached_answer`: the task whose answer first filled the cache.
   All 32 families matched an S2 seed (0 fallbacks).
3. `remember()` each seed into a temporary `Memory` (fresh ChromaDB in a
   temp dir) to obtain real entry ids.
4. Append one echo-log line per cache-hit row via `Memory._log_echo(query,
   entry_id, similarity, hit=True, threshold=0.8)`, using each row's
   `top_similarity`.
5. Run `drift_report(min_hits=3, min_spread=s)` for s in {0.05, 0.08, 0.12}.

Reproduce with:

```bash
.venv/bin/python validation/replay_drift.py
```

## Results

Echo log after replay: 101 recalls analyzed, 32 entries with hits.

| min_spread | candidates flagged | digits family flagged? | rank of digits family | false flags |
|---|---|---|---|---|
| 0.05 | 18 | yes | 1 of 18 | 17 |
| 0.08 (default) | 10 | yes | 1 of 10 | 9 |
| 0.12 | 0 | no | n/a | 0 |

The digits family is detected with:

```
spread=0.1173  hits=4  distinct_queries=4  band=[0.8240, 0.9413]
task="Pull out all digits that appear in: 'She bought 3 apples, 12 eggs, ...'"
```

This matches the expectation in the handoff spec (hits at 0.82 to 0.94,
spread of about 0.12) and the per-task data in `results.md` exactly.

## Reading the numbers honestly

**Recall of the known drift family:** 1/1 at min_spread 0.05 and 0.08;
0/1 at 0.12. The shipped default (0.08) catches it. A 0.12 cutoff misses it
by 0.0027, which is the practical argument for shipping 0.08 rather than a
rounder 0.10 or 0.12.

**Precision:** 1/10 at the default (10%). Nine flagged entries served
correct answers on this run. One of the nine is the "17 multiplied by 24"
entry, which the v0.1.0 judge also flagged wrongly (operand-order judge
error, see `results.md`); the other eight are benign paraphrase families.

**Why precision is structurally deflated on this dataset.** Every seed in
the experiment received exactly four LLM-generated paraphrases by
construction, so nearly every entry that got hits got them across a wide
phrasing range. Wide similarity bands are therefore common and benign here.
Organic production traffic does not guarantee four diverse rephrasings of
every cached task, so a wide band on production data carries more signal
than it does in this replay. The 10% figure is best read as a floor from an
adversarially paraphrase-rich workload, not an estimate of production
precision.

**The margin at the top is thin.** The true drift family ranks first by
spread, but at 0.1173 versus 0.1166 for the benign Gatsby
fiction/non-fiction family. Spread separates "absorbing a broad family"
from "absorbing a narrow one"; it does not by itself separate broad-but-
consistent interpretation from broad-and-divergent interpretation. That is
the structural limit of geometry-only detection.

**What the detector is for, given that limit.** Screening and ranking, not
verdicts. On this run it reduces 32 entries with hits to 10 review
candidates (a 69% reduction) and puts the genuinely drifting entry at the
top of the list, using data that costs nothing to collect. A reviewer (or a
targeted judge pass over only the flagged entries) goes from 101 hit
verifications to 10 entry reviews. Pairing the geometric screen with an
interpretive check on just the candidates is the v0.2 mitigation path
sketched in `results.md`.

## Caveats

1. Entry attribution joins hits to entries via identical `cached_answer`
   strings because the v0.1.0 CSV recorded no entry ids. Exact-string
   collisions between different entries would merge families; none occurred
   here (32 families, 0 seed fallbacks).
2. Similarities are replayed from the CSV, not recomputed; the temporary
   store exists only to mint entry ids and satisfy `still_stored` lookups.
3. Single run, single embedding model, 150 synthetic tasks. Same caveats as
   the parent validation (`results.md`, Known limitations).

## Files

| File | Description |
|---|---|
| `replay_drift.py` | The replay harness (this experiment) |
| `drift_replay.md` | This document |
| `results_threshold_0.8.csv` | Input data (unchanged) |
