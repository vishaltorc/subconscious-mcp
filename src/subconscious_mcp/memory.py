"""Semantic memory backed by ChromaDB + sentence-transformers.

The :class:`Memory` instance owns:
- a persistent ChromaDB collection on disk
- a lazily loaded SentenceTransformer encoder
- a ring buffer of the last 100 recall outcomes for stats
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

import chromadb

from .config import Config


logger = logging.getLogger(__name__)


COLLECTION_NAME = "subconscious"
RING_BUFFER_SIZE = 100


class Memory:
    """Embed, store, retrieve, and forget task -> answer pairs."""

    def __init__(self, config: Config):
        self.config = config
        self._client: chromadb.api.ClientAPI | None = None
        self._collection: Any = None
        self._encoder: Any = None
        self._recent_calls: deque[bool] = deque(maxlen=RING_BUFFER_SIZE)
        self._last_hit_at: float | None = None

    # ---- lazy resources -------------------------------------------------

    @property
    def client(self) -> chromadb.api.ClientAPI:
        if self._client is None:
            storage = self.config.storage_path
            storage.mkdir(parents=True, exist_ok=True)
            logger.info("opening chromadb persistent client at %s", storage)
            self._client = chromadb.PersistentClient(path=str(storage))
        return self._client

    @property
    def collection(self) -> Any:
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    @property
    def encoder(self) -> Any:
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer  # heavy import
            logger.info("loading sentence-transformer model: %s", self.config.embedding_model)
            self._encoder = SentenceTransformer(self.config.embedding_model)
        return self._encoder

    # ---- core ops -------------------------------------------------------

    def embed(self, text: str) -> list[float]:
        """Return a unit-normalized embedding for ``text``."""
        vec = self.encoder.encode(text, normalize_embeddings=True)
        return vec.tolist()

    def remember(
        self,
        task: str,
        answer: str,
        tags: list[str] | None = None,
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Store a (task, answer) pair. Returns ``{stored, entry_id, embedding_dim}``."""
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task must be a non-empty string")
        if not isinstance(answer, str):
            raise ValueError("answer must be a string")

        tags = tags or []
        entry_id = str(uuid.uuid4())
        # embed first (may include a slow first-time model load); then anchor
        # stored_at/expires_at to the moment of the actual write.
        embedding = self.embed(task)
        stored_at = time.time()
        expires_at: float | None = (stored_at + ttl_seconds) if ttl_seconds is not None else None

        metadata: dict[str, Any] = {
            "answer": answer,
            "tags_json": json.dumps(tags),
            "stored_at": stored_at,
            # chromadb metadata can't hold None values directly
            "expires_at": float(expires_at) if expires_at is not None else -1.0,
        }

        self.collection.add(
            ids=[entry_id],
            embeddings=[embedding],
            documents=[task],
            metadatas=[metadata],
        )
        logger.info("remembered entry_id=%s task=%r", entry_id, task[:80])
        return {
            "stored": True,
            "entry_id": entry_id,
            "embedding_dim": len(embedding),
        }

    def recall(
        self,
        task: str,
        threshold: float | None = None,
        top_k: int = 1,
    ) -> dict[str, Any]:
        """Look up the closest non-expired match. Returns hit/miss + best similarity."""
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task must be a non-empty string")
        threshold = threshold if threshold is not None else self.config.default_threshold
        top_k = max(1, int(top_k))

        if self.collection.count() == 0:
            return self._record_miss(0.0)

        query_emb = self.embed(task)
        results = self.collection.query(
            query_embeddings=[query_emb],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        now = time.time()
        best_match: dict[str, Any] | None = None
        best_similarity = 0.0

        for entry_id, distance, document, metadata in zip(ids, distances, documents, metadatas):
            # cosine space: similarity = 1 - distance
            similarity = max(0.0, 1.0 - float(distance))
            expires_at = float(metadata.get("expires_at", -1.0))
            if expires_at > 0 and expires_at <= now:
                logger.debug("skipping expired entry_id=%s", entry_id)
                continue
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = {
                    "entry_id": entry_id,
                    "similarity": similarity,
                    "answer": metadata["answer"],
                    "task_text": document,
                    "stored_at": metadata.get("stored_at"),
                    "tags": json.loads(metadata.get("tags_json", "[]")),
                }

        if best_match is not None and best_match["similarity"] >= threshold:
            return self._record_hit(best_match)
        return self._record_miss(best_similarity)

    def forget(self, entry_id: str) -> dict[str, Any]:
        """Delete an entry. Reports whether it existed."""
        existing = self.collection.get(ids=[entry_id])
        present = bool(existing.get("ids"))
        if present:
            self.collection.delete(ids=[entry_id])
            logger.info("forgot entry_id=%s", entry_id)
        else:
            logger.info("forget called for unknown entry_id=%s", entry_id)
        return {"forgotten": present}

    def stats(self) -> dict[str, Any]:
        """Total entries, last hit timestamp, hit rate over the last 100 recalls."""
        total = self.collection.count()
        recent = list(self._recent_calls)
        hit_rate = (sum(1 for h in recent if h) / len(recent)) if recent else 0.0
        return {
            "total_entries": total,
            "last_hit_at": self._last_hit_at,
            "hit_rate_last_100": round(hit_rate, 4),
        }

    # ---- helpers --------------------------------------------------------

    def _record_hit(self, match: dict[str, Any]) -> dict[str, Any]:
        self._recent_calls.append(True)
        self._last_hit_at = time.time()
        return {
            "hit": True,
            "similarity": match["similarity"],
            "answer": match["answer"],
            "task_text": match["task_text"],
            "entry_id": match["entry_id"],
            "stored_at": match["stored_at"],
            "tags": match["tags"],
        }

    def _record_miss(self, best_sim: float) -> dict[str, Any]:
        self._recent_calls.append(False)
        return {
            "hit": False,
            "similarity": best_sim,
            "answer": None,
            "task_text": None,
            "entry_id": None,
            "stored_at": None,
            "tags": [],
        }
