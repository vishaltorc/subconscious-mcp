"""Tests for the Memory layer."""

from __future__ import annotations

import time

import pytest

from subconscious_mcp.memory import Memory


@pytest.mark.embedding
def test_embed_returns_unit_vector(memory: Memory):
    vec = memory.embed("hello world")
    assert isinstance(vec, list)
    assert len(vec) == 384  # all-MiniLM-L6-v2 produces 384-dim
    # normalize_embeddings=True so |v| should be ~1
    magnitude = sum(x * x for x in vec) ** 0.5
    assert magnitude == pytest.approx(1.0, abs=1e-3)


@pytest.mark.embedding
def test_store_and_recall_exact_match(memory: Memory):
    task = "How do I deploy a Next.js app to Vercel?"
    answer = "Run `vercel --prod` from the project root after `vercel login`."

    stored = memory.remember(task=task, answer=answer)
    assert stored["stored"] is True
    assert stored["embedding_dim"] == 384

    result = memory.recall(task=task, threshold=0.85)
    assert result["hit"] is True
    assert result["answer"] == answer
    assert result["similarity"] > 0.99
    assert result["entry_id"] == stored["entry_id"]
    assert result["task_text"] == task


@pytest.mark.embedding
def test_store_and_recall_paraphrased_match(memory: Memory):
    """Different words, same meaning, should still hit at a modest threshold."""
    original = "How do I deploy a Next.js app to Vercel?"
    paraphrase = "What's the process for shipping a Next.js project on Vercel?"
    answer = "Run vercel --prod after logging in."

    memory.remember(task=original, answer=answer)
    result = memory.recall(task=paraphrase, threshold=0.6)

    assert result["hit"] is True, f"paraphrase missed; similarity={result['similarity']}"
    assert result["answer"] == answer


@pytest.mark.embedding
def test_threshold_above_and_below(memory: Memory):
    memory.remember(
        task="The capital of France is Paris",
        answer="Paris",
    )
    # Very unrelated query => low similarity, should miss at default threshold.
    miss = memory.recall(task="How do I bake sourdough bread?", threshold=0.85)
    assert miss["hit"] is False
    assert miss["answer"] is None
    assert 0.0 <= miss["similarity"] < 0.85

    # Same query lowered to threshold 0.0 should hit (anything > 0 counts).
    relaxed = memory.recall(task="How do I bake sourdough bread?", threshold=0.0)
    # Note: even unrelated text usually has nonzero cosine, so this should hit.
    assert relaxed["hit"] is True
    assert relaxed["similarity"] == miss["similarity"]


@pytest.mark.embedding
def test_forget_removes_entry(memory: Memory):
    stored = memory.remember(task="ephemeral fact", answer="will be deleted")
    entry_id = stored["entry_id"]

    res = memory.forget(entry_id=entry_id)
    assert res["forgotten"] is True

    # Subsequent forget on same id reports False.
    res2 = memory.forget(entry_id=entry_id)
    assert res2["forgotten"] is False

    # And the recall is a miss.
    recalled = memory.recall(task="ephemeral fact", threshold=0.85)
    assert recalled["hit"] is False


@pytest.mark.embedding
def test_ttl_expiry(memory: Memory):
    """An entry with a short TTL is filtered out of recall once expired."""
    memory.remember(
        task="short-lived secret",
        answer="42",
        ttl_seconds=1,
    )

    # immediate recall should hit
    fresh = memory.recall(task="short-lived secret", threshold=0.85)
    assert fresh["hit"] is True
    assert fresh["answer"] == "42"

    # wait past TTL and it should be filtered out
    time.sleep(1.5)
    expired = memory.recall(task="short-lived secret", threshold=0.85)
    assert expired["hit"] is False
    # Note: entry is filtered, not deleted - it still counts toward total_entries.


def test_recall_on_empty_returns_zero_similarity(memory: Memory):
    result = memory.recall(task="anything", threshold=0.5)
    assert result["hit"] is False
    assert result["similarity"] == 0.0
    assert result["answer"] is None


@pytest.mark.embedding
def test_stats_reflects_activity(memory: Memory):
    s0 = memory.stats()
    assert s0["total_entries"] == 0
    assert s0["hit_rate_last_100"] == 0.0
    assert s0["last_hit_at"] is None

    memory.remember(task="alpha", answer="a")
    memory.remember(task="beta", answer="b")

    # one hit, one miss => hit rate 0.5
    memory.recall(task="alpha", threshold=0.85)
    memory.recall(task="completely unrelated nonsense xyz", threshold=0.99)

    s1 = memory.stats()
    assert s1["total_entries"] == 2
    assert s1["hit_rate_last_100"] == pytest.approx(0.5, abs=0.01)
    assert s1["last_hit_at"] is not None


@pytest.mark.embedding
def test_tags_round_trip(memory: Memory):
    memory.remember(
        task="tagged task",
        answer="tagged answer",
        tags=["work", "research"],
    )
    res = memory.recall(task="tagged task", threshold=0.85)
    assert res["hit"] is True
    assert set(res["tags"]) == {"work", "research"}
