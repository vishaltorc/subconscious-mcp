"""tests/test_tags_filter.py"""
from __future__ import annotations

import pytest

from subconscious_mcp.config import Config
from subconscious_mcp.memory import Memory


def _unit(c: float) -> list[float]:
    return [c, (1 - c * c) ** 0.5] + [0.0] * 382


@pytest.fixture
def mem(tmp_path, monkeypatch):
    m = Memory(Config(storage_dir=str(tmp_path / "d")))
    vecs = {
        "work task": _unit(1.0),
        "personal task": _unit(0.97),
        "query": _unit(1.0),
    }
    monkeypatch.setattr(Memory, "embed", lambda self, text: vecs[text])
    return m


def test_recall_tag_filter_excludes_other_tags(mem):
    mem.remember(task="work task", answer="W", tags=["work"])
    mem.remember(task="personal task", answer="P", tags=["personal"])
    hit = mem.recall(task="query", threshold=0.8, top_k=1, tags=["personal"])
    assert hit["hit"] is True
    assert hit["answer"] == "P"


def test_recall_tag_filter_no_match_is_miss(mem):
    mem.remember(task="work task", answer="W", tags=["work"])
    res = mem.recall(task="query", threshold=0.8, tags=["nonexistent"])
    assert res["hit"] is False


def test_echo_tag_filter(mem):
    mem.remember(task="work task", answer="W", tags=["work"])
    mem.remember(task="personal task", answer="P", tags=["personal"])
    pong = mem.echo(task="query", top_k=5, tags=["work"])
    assert [e["task_text"] for e in pong["echoes"]] == ["work task"]
