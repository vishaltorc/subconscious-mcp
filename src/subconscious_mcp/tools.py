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
    """Attach the four subconscious tools to a FastMCP server."""

    @mcp.tool()
    def recall(task: str, threshold: float = 0.85, top_k: int = 1) -> dict[str, Any]:
        """Semantic lookup for a previously remembered task.

        Args:
            task: The task description to search for.
            threshold: Minimum cosine similarity to count as a hit (0-1).
            top_k: How many candidates to consider when picking the best match.

        Returns:
            A dict containing ``hit`` (bool), ``similarity`` (float, best
            observed even on a miss), ``answer`` and ``task_text``/``entry_id``/
            ``stored_at`` when ``hit`` is True.
        """
        logger.debug("tool recall task=%r threshold=%s top_k=%s", task[:80], threshold, top_k)
        try:
            return memory.recall(task=task, threshold=threshold, top_k=top_k)
        except Exception:
            logger.exception("recall failed")
            raise

    @mcp.tool()
    def remember(
        task: str,
        answer: str,
        tags: list[str] | None = None,
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Persist a (task, answer) pair so a future recall can find it.

        Args:
            task: The task this answer applies to.
            answer: The answer/result to remember.
            tags: Optional labels for grouping or future filtering.
            ttl_seconds: Optional time-to-live; entry is filtered out of
                recalls after this many seconds.

        Returns:
            ``{"stored": True, "entry_id": ..., "embedding_dim": ...}``.
        """
        logger.debug("tool remember task=%r tags=%s ttl=%s", task[:80], tags, ttl_seconds)
        try:
            return memory.remember(
                task=task,
                answer=answer,
                tags=tags or [],
                ttl_seconds=ttl_seconds,
            )
        except Exception:
            logger.exception("remember failed")
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
