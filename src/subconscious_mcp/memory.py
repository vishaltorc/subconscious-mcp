"""Semantic memory backed by ChromaDB + sentence-transformers.

The :class:`Memory` instance owns:
- a persistent ChromaDB collection on disk
- a lazily loaded SentenceTransformer encoder
- a ring buffer of the last 100 recall outcomes for stats
- an append-only echo log (JSONL) recording every recall's nearest
  neighbour and similarity, used by :meth:`drift_report` to surface
  first-fill semantic drift candidates
"""

from __future__ import annotations

import json
import logging
import os
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
ECHO_LOG_FILENAME = "echo_log.jsonl"


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
    def echo_log_path(self) -> Path:
        return self.config.storage_path / ECHO_LOG_FILENAME

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
            self._log_echo(task, None, 0.0, False, threshold)
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
            self._log_echo(task, best_match["entry_id"], best_match["similarity"], True, threshold)
            return self._record_hit(best_match)
        nearest_id = best_match["entry_id"] if best_match is not None else None
        self._log_echo(task, nearest_id, best_similarity, False, threshold)
        return self._record_miss(best_similarity)

    def echo(self, task: str, top_k: int = 5) -> dict[str, Any]:
        """Sonar ping: return the nearest non-expired entries WITHOUT answers.

        Unlike :meth:`recall`, this returns geometry, not content: the caller
        learns how close the query sits to known territory but cannot absorb
        a cached answer. Echo calls are not counted in the hit-rate ring
        buffer and are not written to the echo log.
        """
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task must be a non-empty string")
        top_k = max(1, int(top_k))

        total = self.collection.count()
        if total == 0:
            return {"count": 0, "echoes": []}

        query_emb = self.embed(task)
        results = self.collection.query(
            query_embeddings=[query_emb],
            n_results=min(top_k, total),
            include=["documents", "metadatas", "distances"],
        )

        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        now = time.time()
        echoes: list[dict[str, Any]] = []
        for entry_id, distance, document, metadata in zip(ids, distances, documents, metadatas):
            similarity = max(0.0, 1.0 - float(distance))
            expires_at = float(metadata.get("expires_at", -1.0))
            if expires_at > 0 and expires_at <= now:
                continue
            echoes.append({
                "entry_id": entry_id,
                "similarity": similarity,
                "task_text": document,
                "stored_at": metadata.get("stored_at"),
                "tags": json.loads(metadata.get("tags_json", "[]")),
            })

        echoes.sort(key=lambda e: e["similarity"], reverse=True)
        return {"count": total, "echoes": echoes}

    def drift_report(self, min_hits: int = 3, min_spread: float = 0.08) -> dict[str, Any]:
        """Surface first-fill semantic drift candidates from the echo log.

        An entry whose recorded hits span a wide similarity band has absorbed
        a broad family of differently-phrased queries; the wider the band,
        the higher the risk that one cached answer is serving queries with
        subtly different interpretations.
        """
        min_hits = max(1, int(min_hits))
        min_spread = float(min_spread)

        records = self._read_echo_log()
        hits_by_entry: dict[str, list[dict[str, Any]]] = {}
        for rec in records:
            entry_id = rec.get("entry_id")
            if rec.get("hit") and entry_id:
                hits_by_entry.setdefault(str(entry_id), []).append(rec)

        candidates: list[dict[str, Any]] = []
        for entry_id, recs in hits_by_entry.items():
            sims = [float(r.get("similarity", 0.0)) for r in recs]
            queries = {" ".join(str(r.get("query", "")).lower().split()) for r in recs}
            spread = max(sims) - min(sims)
            if len(recs) < min_hits or spread < min_spread or len(queries) < 2:
                continue
            existing = self.collection.get(ids=[entry_id])
            present = bool(existing.get("ids"))
            documents = existing.get("documents") or []
            candidates.append({
                "entry_id": entry_id,
                "task_text": documents[0] if present and documents else None,
                "still_stored": present,
                "hits": len(recs),
                "distinct_queries": len(queries),
                "similarity_min": round(min(sims), 4),
                "similarity_max": round(max(sims), 4),
                "similarity_spread": round(spread, 4),
            })

        candidates.sort(key=lambda c: c["similarity_spread"], reverse=True)
        return {
            "analyzed_recalls": len(records),
            "entries_with_hits": len(hits_by_entry),
            "candidates": candidates,
        }

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

    # ---- echo log -------------------------------------------------------

    def _log_echo(
        self,
        query: str,
        entry_id: str | None,
        similarity: float,
        hit: bool,
        threshold: float,
    ) -> None:
        """Append one recall outcome to the echo log. Must never break recall."""
        if not self.config.echo_log_enabled:
            return
        try:
            record = {
                "ts": time.time(),
                "query": query,
                "entry_id": entry_id,
                "similarity": round(float(similarity), 6),
                "hit": hit,
                "threshold": round(float(threshold), 6),
            }
            path = self.echo_log_path
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            if path.stat().st_size > self.config.echo_log_max_bytes:
                self._compact_echo_log(path)
        except Exception:
            logger.exception("echo log write failed")

    def _compact_echo_log(self, path: Path) -> None:
        """Halve the log by dropping the oldest lines. Atomic via os.replace."""
        lines = path.read_text(encoding="utf-8").splitlines()
        keep = lines[len(lines) // 2:]
        tmp = path.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
        os.replace(tmp, path)
        logger.info("compacted echo log: %d -> %d lines", len(lines), len(keep))

    def _read_echo_log(self) -> list[dict[str, Any]]:
        """Parse the echo log, tolerating torn or corrupt lines."""
        path = self.echo_log_path
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                records.append(rec)
        return records

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
