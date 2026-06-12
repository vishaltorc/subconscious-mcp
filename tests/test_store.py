"""tests/test_store.py"""
from __future__ import annotations

from pathlib import Path

from subconscious_mcp.store import EpisodeStore


def make(tmp_path: Path) -> EpisodeStore:
    return EpisodeStore(tmp_path / "context.db")


def test_add_and_pending_roundtrip(tmp_path):
    s = make(tmp_path)
    eid = s.add_episode(namespace="proj", project="/x", session_id="s1",
                        content="did a thing", source="stop_hook")
    rows = s.pending_episodes(limit=10)
    assert [r["id"] for r in rows] == [eid]
    assert rows[0]["content"] == "did a thing"


def test_mark_ingested_removes_from_pending(tmp_path):
    s = make(tmp_path)
    eid = s.add_episode(namespace="p", project="/x", session_id="s", content="c", source="t")
    s.mark("ingested", [eid])
    assert s.pending_episodes(limit=10) == []


def test_recent_episodes_namespace_scoped_and_ordered(tmp_path):
    s = make(tmp_path)
    s.add_episode(namespace="a", project="/x", session_id="1", content="old", source="t", ts=100.0)
    s.add_episode(namespace="a", project="/x", session_id="2", content="new", source="t", ts=200.0)
    s.add_episode(namespace="b", project="/y", session_id="3", content="other", source="t",
                  ts=300.0)
    got = s.recent_episodes(namespace="a", n=5)
    assert [r["content"] for r in got] == ["new", "old"]


def test_count_for_namespace(tmp_path):
    s = make(tmp_path)
    s.add_episode(namespace="a", project="/x", session_id="1", content="c", source="t")
    assert s.count_for_namespace("a") == 1
    assert s.count_for_namespace("zz") == 0


def test_two_connections_wal_concurrent_write(tmp_path):
    # hooks + server may write/read concurrently; WAL must allow it
    s1 = make(tmp_path)
    s2 = EpisodeStore(tmp_path / "context.db")
    s1.add_episode(namespace="a", project="/x", session_id="1", content="one", source="t")
    s2.add_episode(namespace="a", project="/x", session_id="2", content="two", source="t")
    assert s1.count_for_namespace("a") == 2


def test_journal_mode_is_wal(tmp_path):
    import sqlite3
    make(tmp_path)
    mode = sqlite3.connect(tmp_path / "context.db").execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"


def test_writer_succeeds_during_open_read_transaction(tmp_path):
    # the real scenario: a hook writes while the server holds a read snapshot.
    # In WAL this succeeds; in rollback-journal modes the writer would get
    # "database is locked".
    import sqlite3
    s = make(tmp_path)
    s.add_episode(namespace="a", project="/x", session_id="0", content="seed", source="t")
    reader = sqlite3.connect(tmp_path / "context.db")
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT * FROM episodes").fetchall()  # hold a read snapshot
        s.add_episode(namespace="a", project="/x", session_id="1", content="while-reading",
                      source="t")
    finally:
        reader.rollback()
        reader.close()
    assert s.count_for_namespace("a") == 2
