"""Tests for the echolocation layer: echo(), the echo log, and drift_report()."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from subconscious_mcp.config import Config
from subconscious_mcp.memory import Memory


def _write_log_lines(memory: Memory, records: list[dict]) -> None:
    """Write synthetic echo-log records directly, bypassing recall."""
    path = memory.echo_log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


# ---- echo() ---------------------------------------------------------------


def test_echo_returns_neighbors_without_answers(memory: Memory):
    memory.remember(task="How do I deploy a Next.js app to Vercel?", answer="vercel --prod")
    memory.remember(task="How do I bake sourdough bread?", answer="flour, water, salt, time")
    memory.remember(task="What is the capital of France?", answer="Paris")

    result = memory.echo(task="Deploying a Next.js project to Vercel", top_k=3)

    assert result["count"] == 3
    assert 1 <= len(result["echoes"]) <= 3
    for e in result["echoes"]:
        assert set(e) == {"entry_id", "similarity", "task_text", "stored_at", "tags"}
        assert "answer" not in e
    # sorted by similarity descending; nearest is the Vercel entry
    sims = [e["similarity"] for e in result["echoes"]]
    assert sims == sorted(sims, reverse=True)
    assert "Vercel" in result["echoes"][0]["task_text"]


def test_echo_on_empty_collection(memory: Memory):
    result = memory.echo(task="anything at all")
    assert result == {"count": 0, "echoes": []}


def test_echo_excludes_expired(memory: Memory):
    memory.remember(task="short-lived ping target", answer="42", ttl_seconds=1)
    time.sleep(1.5)
    result = memory.echo(task="short-lived ping target", top_k=5)
    assert result["count"] == 1  # filtered, not deleted
    assert result["echoes"] == []


def test_echo_does_not_affect_stats_or_log(memory: Memory):
    memory.remember(task="alpha", answer="a")
    memory.echo(task="alpha")

    s = memory.stats()
    assert s["hit_rate_last_100"] == 0.0
    assert s["last_hit_at"] is None
    assert not memory.echo_log_path.exists()


def test_echo_rejects_empty_task(memory: Memory):
    with pytest.raises(ValueError):
        memory.echo(task="   ")


# ---- echo log -------------------------------------------------------------


def test_recall_writes_echo_log(memory: Memory):
    stored = memory.remember(task="the sky is blue", answer="atmosphere scatters light")

    memory.recall(task="the sky is blue", threshold=0.85)  # hit
    memory.recall(task="what is the capital of mongolia?", threshold=0.95)  # miss

    records = memory._read_echo_log()
    assert len(records) == 2

    hit_rec, miss_rec = records
    assert hit_rec["hit"] is True
    assert hit_rec["entry_id"] == stored["entry_id"]
    assert hit_rec["query"] == "the sky is blue"
    assert hit_rec["similarity"] >= 0.85
    assert hit_rec["threshold"] == 0.85

    assert miss_rec["hit"] is False
    assert miss_rec["entry_id"] == stored["entry_id"]  # nearest neighbour, even on miss
    assert 0.0 <= miss_rec["similarity"] < 0.95


def test_recall_on_empty_collection_logs_null_entry(memory: Memory):
    memory.recall(task="anything", threshold=0.5)
    records = memory._read_echo_log()
    assert len(records) == 1
    assert records[0]["hit"] is False
    assert records[0]["entry_id"] is None
    assert records[0]["similarity"] == 0.0


def test_echo_log_disabled(tmp_path: Path):
    config = Config(
        storage_dir=str(tmp_path / "data"),
        log_level="WARNING",
        echo_log_enabled=False,
    )
    memory = Memory(config)
    memory.recall(task="anything", threshold=0.5)
    assert not memory.echo_log_path.exists()
    assert memory._read_echo_log() == []


def test_echo_log_compaction(tmp_path: Path):
    config = Config(
        storage_dir=str(tmp_path / "data"),
        log_level="WARNING",
        echo_log_max_bytes=1_000,
    )
    memory = Memory(config)
    for i in range(40):
        memory._log_echo(f"synthetic query number {i}", None, 0.5, False, 0.85)

    records = memory._read_echo_log()
    assert 0 < len(records) < 40
    assert memory.echo_log_path.stat().st_size <= 1_000
    # the newest record survives compaction
    assert records[-1]["query"] == "synthetic query number 39"


# ---- drift_report() -------------------------------------------------------


def test_drift_report_empty(memory: Memory):
    report = memory.drift_report()
    assert report == {"analyzed_recalls": 0, "entries_with_hits": 0, "candidates": []}


def test_drift_report_flags_wide_band_entry(memory: Memory):
    stored = memory.remember(
        task="Pull out all digits from the milk-and-eggs sentence",
        answer="Digits found: 3, 1, 2, 2.",
    )
    eid = stored["entry_id"]
    now = time.time()
    _write_log_lines(memory, [
        {"ts": now, "query": "pull out all digits", "entry_id": eid,
         "similarity": 0.94, "hit": True, "threshold": 0.8},
        {"ts": now, "query": "extract every number", "entry_id": eid,
         "similarity": 0.82, "hit": True, "threshold": 0.8},
        {"ts": now, "query": "list the numbers in the sentence", "entry_id": eid,
         "similarity": 0.86, "hit": True, "threshold": 0.8},
    ])

    report = memory.drift_report(min_hits=3, min_spread=0.08)
    assert report["analyzed_recalls"] == 3
    assert report["entries_with_hits"] == 1
    assert len(report["candidates"]) == 1

    cand = report["candidates"][0]
    assert cand["entry_id"] == eid
    assert cand["still_stored"] is True
    assert cand["task_text"] == "Pull out all digits from the milk-and-eggs sentence"
    assert cand["hits"] == 3
    assert cand["distinct_queries"] == 3
    assert cand["similarity_min"] == 0.82
    assert cand["similarity_max"] == 0.94
    assert cand["similarity_spread"] == pytest.approx(0.12, abs=1e-4)


def test_drift_report_ignores_narrow_band_and_few_hits(memory: Memory):
    now = time.time()
    _write_log_lines(memory, [
        # narrow band: three distinct queries but spread 0.005 < min_spread
        {"ts": now, "query": "q one", "entry_id": "narrow-id",
         "similarity": 0.960, "hit": True, "threshold": 0.8},
        {"ts": now, "query": "q two", "entry_id": "narrow-id",
         "similarity": 0.962, "hit": True, "threshold": 0.8},
        {"ts": now, "query": "q three", "entry_id": "narrow-id",
         "similarity": 0.965, "hit": True, "threshold": 0.8},
        # wide band but only 2 hits < min_hits
        {"ts": now, "query": "r one", "entry_id": "few-id",
         "similarity": 0.81, "hit": True, "threshold": 0.8},
        {"ts": now, "query": "r two", "entry_id": "few-id",
         "similarity": 0.95, "hit": True, "threshold": 0.8},
        # misses never count
        {"ts": now, "query": "m one", "entry_id": "miss-id",
         "similarity": 0.5, "hit": False, "threshold": 0.8},
    ])

    report = memory.drift_report(min_hits=3, min_spread=0.08)
    assert report["analyzed_recalls"] == 6
    assert report["entries_with_hits"] == 2
    assert report["candidates"] == []


def test_drift_report_handles_forgotten_entry(memory: Memory):
    now = time.time()
    _write_log_lines(memory, [
        {"ts": now, "query": "phrasing a", "entry_id": "gone-id",
         "similarity": 0.95, "hit": True, "threshold": 0.8},
        {"ts": now, "query": "phrasing b", "entry_id": "gone-id",
         "similarity": 0.83, "hit": True, "threshold": 0.8},
        {"ts": now, "query": "phrasing c", "entry_id": "gone-id",
         "similarity": 0.88, "hit": True, "threshold": 0.8},
    ])

    report = memory.drift_report(min_hits=3, min_spread=0.08)
    assert len(report["candidates"]) == 1
    cand = report["candidates"][0]
    assert cand["still_stored"] is False
    assert cand["task_text"] is None


def test_drift_report_tolerates_corrupt_lines(memory: Memory):
    path = memory.echo_log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write("{not valid json\n")
        f.write("\n")
        f.write('"a bare string"\n')
        f.write(json.dumps({"ts": time.time(), "query": "ok", "entry_id": None,
                            "similarity": 0.1, "hit": False, "threshold": 0.85}) + "\n")

    report = memory.drift_report()
    assert report["analyzed_recalls"] == 1
    assert report["candidates"] == []
