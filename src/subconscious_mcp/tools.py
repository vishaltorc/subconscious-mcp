"""MCP tool definitions.

Each tool is a thin shim over :class:`subconscious_mcp.memory.Memory`. Keeping
the logic in ``Memory`` lets unit tests bypass the MCP transport entirely.
"""

from __future__ import annotations

import logging
from typing import Any

from .memory import Memory

logger = logging.getLogger(__name__)


def register_tools(mcp: Any, memory: Memory) -> None:
    """Attach the six subconscious tools to a FastMCP server."""

    @mcp.tool()
    def recall(
        task: str,
        threshold: float = 0.85,
        top_k: int = 1,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Semantic lookup for a previously remembered task.

        Args:
            task: The task description to search for.
            threshold: Minimum cosine similarity to count as a hit (0-1).
            top_k: How many candidates to consider when picking the best match.
            tags: optional; a candidate must share at least one of these tags.

        Returns:
            A dict containing ``hit`` (bool), ``similarity`` (float, best
            observed even on a miss), ``answer`` and ``task_text``/``entry_id``/
            ``stored_at`` when ``hit`` is True.
        """
        logger.debug("tool recall task=%r threshold=%s top_k=%s", task[:80], threshold, top_k)
        try:
            return memory.recall(task=task, threshold=threshold, top_k=top_k, tags=tags)
        except Exception:
            logger.exception("recall failed")
            raise

    @mcp.tool()
    def remember(
        task: str,
        answer: str,
        tags: list[str] | None = None,
        ttl_seconds: int | None = None,
        skip_if_duplicate: bool = False,
    ) -> dict[str, Any]:
        """Persist a (task, answer) pair so a future recall can find it.

        Args:
            task: The task this answer applies to.
            answer: The answer/result to remember.
            tags: Optional labels for grouping or future filtering.
            ttl_seconds: Optional time-to-live; entry is filtered out of
                recalls after this many seconds.
            skip_if_duplicate: When True, skip the write if the nearest
                curated entry is a near-duplicate (similarity in the band
                ``[0.75, 0.92]``); returns ``{"stored": False, ...}`` instead.

        Returns:
            ``{"stored": True, "entry_id": ..., "embedding_dim": ...}``. If the
            nearest curated entry's cosine similarity falls in the
            near-duplicate band ``[0.75, 0.92]``, the result also carries
            ``warning="near_duplicate"`` with ``nearest_task``,
            ``nearest_similarity``, and ``nearest_entry_id`` (a write-time
            first-fill drift guard). Ambient episodes never trigger it.
        """
        logger.debug("tool remember task=%r tags=%s ttl=%s", task[:80], tags, ttl_seconds)
        try:
            return memory.remember(
                task=task,
                answer=answer,
                tags=tags or [],
                ttl_seconds=ttl_seconds,
                skip_if_duplicate=skip_if_duplicate,
            )
        except Exception:
            logger.exception("remember failed")
            raise

    @mcp.tool()
    def echo(task: str, top_k: int = 5, tags: list[str] | None = None) -> dict[str, Any]:
        """Sonar ping: find the nearest remembered entries WITHOUT their answers.

        Use this to sense whether a task sits in known territory before
        committing to a recall. Because no answer is returned, an echo can
        never propagate a stale or wrong cached answer.

        Args:
            task: The task description to ping with.
            top_k: How many nearest entries to report.
            tags: optional; a candidate must share at least one of these tags.

        Returns:
            ``{"count": total_entries, "echoes": [{entry_id, similarity,
            task_text, stored_at, tags}, ...]}`` sorted by similarity
            descending. Expired entries are excluded.
        """
        logger.debug("tool echo task=%r top_k=%s", task[:80], top_k)
        try:
            return memory.echo(task=task, top_k=top_k, tags=tags)
        except Exception:
            logger.exception("echo failed")
            raise

    @mcp.tool()
    def drift_report(min_hits: int = 3, min_spread: float = 0.08) -> dict[str, Any]:
        """Detect first-fill semantic drift candidates from the echo log.

        Flags entries whose recall hits span a wide similarity band across
        distinct query phrasings: a sign that one cached answer is absorbing
        a family of queries that may carry different interpretations.

        Args:
            min_hits: Minimum recorded hits before an entry is considered.
            min_spread: Minimum (max - min) hit similarity band to flag.

        Returns:
            ``{"analyzed_recalls": int, "entries_with_hits": int,
            "candidates": [{entry_id, task_text, still_stored, hits,
            distinct_queries, similarity_min, similarity_max,
            similarity_spread}, ...]}`` sorted by spread descending.
        """
        logger.debug("tool drift_report min_hits=%s min_spread=%s", min_hits, min_spread)
        try:
            return memory.drift_report(min_hits=min_hits, min_spread=min_spread)
        except Exception:
            logger.exception("drift_report failed")
            raise

    @mcp.tool()
    def forget(entry_id: str) -> dict[str, Any]:
        """Delete a remembered entry by id.

        Args:
            entry_id: The id returned by a prior ``remember`` call.

        Returns:
            ``{"forgotten": True}`` if the entry existed, else False.
        """
        logger.debug("tool forget entry_id=%s", entry_id)
        try:
            return memory.forget(entry_id=entry_id)
        except Exception:
            logger.exception("forget failed")
            raise

    @mcp.tool()
    def stats() -> dict[str, Any]:
        """Server statistics.

        Returns:
            ``{"total_entries": int, "last_hit_at": float|None, "hit_rate_last_100": float}``.
        """
        try:
            return memory.stats()
        except Exception:
            logger.exception("stats failed")
            raise
