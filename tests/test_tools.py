"""End-to-end tests for the six MCP tools via a mocked FastMCP transport."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from subconscious_mcp.memory import Memory
from subconscious_mcp.tools import register_tools

# Every test here exercises remember/recall through the tool layer, so the
# whole module needs the sentence-transformers model.
pytestmark = pytest.mark.embedding


class FakeMCP:
    """Minimal FastMCP stand-in: captures @mcp.tool() registrations."""

    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., Any]] = {}

    def tool(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[fn.__name__] = fn
            return fn
        return decorator


@pytest.fixture
def wired(memory: Memory) -> tuple[FakeMCP, Memory]:
    mcp = FakeMCP()
    register_tools(mcp, memory)
    return mcp, memory


def test_all_six_tools_registered(wired: tuple[FakeMCP, Memory]):
    mcp, _ = wired
    assert set(mcp.tools) == {"recall", "remember", "echo", "drift_report", "forget", "stats"}


def test_tool_remember_then_recall(wired: tuple[FakeMCP, Memory]):
    mcp, _ = wired
    remembered = mcp.tools["remember"](
        task="Where does Vercel store project env vars?",
        answer="In the Vercel dashboard under Project Settings -> Environment Variables.",
        tags=["vercel", "ops"],
    )
    assert remembered["stored"] is True
    assert "entry_id" in remembered

    hit = mcp.tools["recall"](
        task="Where does Vercel store project env vars?",
        threshold=0.85,
        top_k=1,
    )
    assert hit["hit"] is True
    assert hit["entry_id"] == remembered["entry_id"]


def test_tool_recall_miss_reports_best_similarity(wired: tuple[FakeMCP, Memory]):
    mcp, _ = wired
    mcp.tools["remember"](task="the sky is blue", answer="atmosphere scatters light")

    miss = mcp.tools["recall"](
        task="what is the capital of mongolia?",
        threshold=0.95,
        top_k=1,
    )
    assert miss["hit"] is False
    assert 0.0 <= miss["similarity"] < 0.95
    assert miss["answer"] is None


def test_tool_forget_returns_correct_flag(wired: tuple[FakeMCP, Memory]):
    mcp, _ = wired
    stored = mcp.tools["remember"](task="forget me", answer="ok")
    eid = stored["entry_id"]

    res = mcp.tools["forget"](entry_id=eid)
    assert res["forgotten"] is True

    res2 = mcp.tools["forget"](entry_id=eid)
    assert res2["forgotten"] is False


def test_tool_stats_after_mix_of_hits_and_misses(wired: tuple[FakeMCP, Memory]):
    mcp, _ = wired
    mcp.tools["remember"](task="alpha", answer="a")
    mcp.tools["recall"](task="alpha", threshold=0.85)
    mcp.tools["recall"](task="zzz nope", threshold=0.99)

    s = mcp.tools["stats"]()
    assert s["total_entries"] == 1
    assert 0.0 <= s["hit_rate_last_100"] <= 1.0
    assert s["last_hit_at"] is not None


def test_tool_echo_returns_geometry_only(wired: tuple[FakeMCP, Memory]):
    mcp, _ = wired
    mcp.tools["remember"](task="the sky is blue", answer="atmosphere scatters light")

    pong = mcp.tools["echo"](task="why is the sky blue?", top_k=3)
    assert pong["count"] == 1
    assert len(pong["echoes"]) == 1
    assert "answer" not in pong["echoes"][0]
    assert pong["echoes"][0]["task_text"] == "the sky is blue"
    assert 0.0 <= pong["echoes"][0]["similarity"] <= 1.0


def test_tool_drift_report_after_recalls(wired: tuple[FakeMCP, Memory]):
    mcp, _ = wired
    mcp.tools["remember"](task="alpha", answer="a")
    mcp.tools["recall"](task="alpha", threshold=0.85)

    report = mcp.tools["drift_report"](min_hits=1, min_spread=0.0)
    assert report["analyzed_recalls"] == 1
    assert report["entries_with_hits"] == 1
    # one hit from one distinct query is never a drift candidate
    assert report["candidates"] == []
