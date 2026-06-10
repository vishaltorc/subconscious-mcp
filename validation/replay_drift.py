"""Replay the threshold-0.8 validation run through the echo log and ask
drift_report to find the first-fill semantic drift family.

The validation experiment (results_threshold_0.8.csv) predates the echo log:
v0.1.0 had no record of which entry served each cache hit. This script
reconstructs that record after the fact, then runs the v0.2.0 detector on it.

Reconstruction logic:
- Cache-hit rows are those with system_used == "S1". The CSV has no explicit
  "matched entry" column, so hits are joined to entries via the cached_answer
  string: every hit that returned the same answer was served by the same
  stored entry.
- The entry's stored task text is the first S2 row (file order) carrying the
  same cached_answer: that is the task whose answer first filled the cache
  for the family.
- Each reconstructed seed is remember()ed into a temporary Memory so real
  entry ids exist, then one echo-log line is appended per cache-hit row via
  Memory._log_echo (private, but it keeps the log format canonical).

Run:  .venv/bin/python validation/replay_drift.py
"""

from __future__ import annotations

import csv
import sys
import tempfile
from collections import OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from subconscious_mcp.config import Config  # noqa: E402
from subconscious_mcp.memory import Memory  # noqa: E402

CSV_PATH = REPO_ROOT / "validation" / "results_threshold_0.8.csv"
THRESHOLD = 0.8  # the run being replayed
MIN_HITS = 3
SPREAD_SWEEP = [0.05, 0.08, 0.12]
DRIFT_SEED_PREFIX = "Pull out all digits"  # the known first-fill family


def load_rows() -> list[dict[str, str]]:
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def reconstruct_families(rows: list[dict[str, str]]):
    """Map cached_answer -> {seed_task, hits:[(query, similarity), ...]}."""
    families: "OrderedDict[str, dict]" = OrderedDict()
    for row in rows:
        if row["system_used"] != "S1":
            continue
        answer = row["cached_answer"]
        fam = families.setdefault(answer, {"seed_task": None, "hits": []})
        fam["hits"].append((row["task_text"], float(row["top_similarity"])))

    unmatched = 0
    for row in rows:
        if row["system_used"] != "S2":
            continue
        answer = row["cached_answer"]
        if answer in families and families[answer]["seed_task"] is None:
            families[answer]["seed_task"] = row["task_text"]

    for answer, fam in families.items():
        if fam["seed_task"] is None:
            # No S2 row carries this answer (should not happen); fall back to
            # the first hit's own text so the replay can still proceed.
            fam["seed_task"] = fam["hits"][0][0]
            unmatched += 1
    return families, unmatched


def main() -> int:
    rows = load_rows()
    families, unmatched = reconstruct_families(rows)
    n_hits = sum(len(f["hits"]) for f in families.values())
    print(f"rows={len(rows)} cache_hits={n_hits} families={len(families)} "
          f"seed_fallbacks={unmatched}")

    with tempfile.TemporaryDirectory(prefix="subconscious-replay-") as tmp:
        memory = Memory(Config(storage_dir=tmp))

        # 1. Store each family's seed so a real entry id exists.
        entry_by_answer: dict[str, str] = {}
        for answer, fam in families.items():
            stored = memory.remember(task=fam["seed_task"], answer=answer)
            entry_by_answer[answer] = stored["entry_id"]

        # 2. Append one echo-log line per historical cache hit.
        for answer, fam in families.items():
            entry_id = entry_by_answer[answer]
            for query, similarity in fam["hits"]:
                memory._log_echo(query, entry_id, similarity, True, THRESHOLD)

        # 3. Run the detector across the spread sweep.
        drift_entry_id = next(
            (eid for ans, eid in entry_by_answer.items()
             if families[ans]["seed_task"].startswith(DRIFT_SEED_PREFIX)),
            None,
        )
        print(f"known drift family entry_id: {drift_entry_id}")

        for min_spread in SPREAD_SWEEP:
            report = memory.drift_report(min_hits=MIN_HITS, min_spread=min_spread)
            flagged = report["candidates"]
            drift_flagged = any(c["entry_id"] == drift_entry_id for c in flagged)
            print(f"\n=== drift_report(min_hits={MIN_HITS}, min_spread={min_spread}) ===")
            print(f"analyzed_recalls={report['analyzed_recalls']} "
                  f"entries_with_hits={report['entries_with_hits']} "
                  f"candidates={len(flagged)} "
                  f"digits_family_flagged={drift_flagged}")
            for c in flagged:
                marker = " <-- KNOWN DRIFT" if c["entry_id"] == drift_entry_id else ""
                print(f"  spread={c['similarity_spread']:.4f} "
                      f"hits={c['hits']} distinct={c['distinct_queries']} "
                      f"band=[{c['similarity_min']:.4f}, {c['similarity_max']:.4f}] "
                      f"task={c['task_text'][:60]!r}{marker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
