"""tests/test_near_duplicate.py"""
from __future__ import annotations

import pytest

from subconscious_mcp.config import Config
from subconscious_mcp.memory import Memory


def _unit(c: float) -> list[float]:
    return [c, (1 - c * c) ** 0.5] + [0.0] * 382


@pytest.fixture
def mem(tmp_path, monkeypatch):
    m = Memory(Config(storage_dir=str(tmp_path / "d")))
    vecs = {"pull out digits": _unit(1.0), "extract numbers": _unit(0.85), "unrelated": _unit(0.1)}
    monkeypatch.setattr(Memory, "embed", lambda self, text: vecs[text])
    return m


def test_warns_in_band_and_still_stores(mem):
    mem.remember(task="pull out digits", answer="1,2,3")
    res = mem.remember(task="extract numbers", answer="3,12,2")
    assert res["stored"] is True
    assert res["warning"] == "near_duplicate"
    assert res["nearest_task"] == "pull out digits"
    assert 0.75 <= res["nearest_similarity"] <= 0.92


def test_skip_if_duplicate(mem):
    mem.remember(task="pull out digits", answer="1,2,3")
    res = mem.remember(task="extract numbers", answer="x", skip_if_duplicate=True)
    assert res["stored"] is False
    assert res["warning"] == "near_duplicate"
    assert mem.collection.count() == 1


def test_no_warning_outside_band(mem):
    mem.remember(task="pull out digits", answer="1,2,3")
    res = mem.remember(task="unrelated", answer="y")
    assert res["stored"] is True
    assert "warning" not in res


def test_episodes_do_not_trigger_warning(mem):
    # an ingested episode at 0.85 must not count as a duplicate of curated memory
    mem.collection.add(ids=["episode-1"], embeddings=[_unit(0.85)], documents=["ep"],
                       metadatas=[{"stored_at": 0.0, "expires_at": -1.0,
                                   "tags_json": "[]", "kind": "episode"}])
    res = mem.remember(task="pull out digits", answer="1,2,3")
    assert "warning" not in res
