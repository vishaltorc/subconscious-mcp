"""tests/test_ingest.py"""
from __future__ import annotations

import pytest

from subconscious_mcp.config import Config
from subconscious_mcp.memory import Memory
from subconscious_mcp.store import EpisodeStore


def _unit(c: float) -> list[float]:
    return [c, (1 - c * c) ** 0.5] + [0.0] * 382


@pytest.fixture
def mem(tmp_path, monkeypatch):
    m = Memory(Config(storage_dir=str(tmp_path / "d")))
    monkeypatch.setattr(Memory, "embed", lambda self, text: _unit(1.0))
    return m


def test_ingest_pending_moves_episodes_to_chroma(mem):
    store = EpisodeStore(mem.config.storage_path / "context.db")
    store.add_episode(namespace="default", project="/x", session_id="s",
                      content="TASK: t\nOUTCOME: o", source="stop_hook")
    result = mem.ingest_pending()
    assert result == {"ingested": 1}
    assert store.pending_episodes() == []
    assert mem.collection.count() == 1


def test_ingest_only_own_namespace(mem):
    store = EpisodeStore(mem.config.storage_path / "context.db")
    store.add_episode(namespace="otherns", project="/x", session_id="s",
                      content="c", source="t")
    assert mem.ingest_pending() == {"ingested": 0}
    assert len(store.pending_episodes()) == 1


def test_recall_never_answers_from_episodes(mem):
    store = EpisodeStore(mem.config.storage_path / "context.db")
    store.add_episode(namespace="default", project="/x", session_id="s",
                      content="TASK: t\nOUTCOME: o", source="stop_hook")
    mem.ingest_pending()
    res = mem.recall(task="anything", threshold=0.5)
    assert res["hit"] is False


def test_echo_sees_episodes(mem):
    store = EpisodeStore(mem.config.storage_path / "context.db")
    store.add_episode(namespace="default", project="/x", session_id="s",
                      content="TASK: t\nOUTCOME: o", source="stop_hook")
    mem.ingest_pending()
    pong = mem.echo(task="anything", top_k=5)
    assert pong["count"] == 1
    assert len(pong["echoes"]) == 1
