"""src/subconscious_mcp/store.py

SQLite episode store: the context inbox. Hooks and CLI write here; the MCP
server ingests from here. This module is the ONLY code that touches
context.db, and it must stay import-light (stdlib only) because hooks
import it.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    namespace TEXT NOT NULL,
    project TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'ingested', 'skipped'))
);
CREATE INDEX IF NOT EXISTS idx_episodes_ns_ts ON episodes (namespace, ts DESC);
CREATE INDEX IF NOT EXISTS idx_episodes_status ON episodes (status);
"""


class EpisodeStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        return conn

    def add_episode(self, *, namespace: str, project: str, session_id: str,
                    content: str, source: str, ts: float | None = None) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO episodes (ts, namespace, project, session_id, content, source)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (ts if ts is not None else time.time(), namespace, project,
                 session_id, content, source),
            )
            return int(cur.lastrowid)

    def pending_episodes(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM episodes WHERE status = 'pending' ORDER BY id LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def mark(self, status: str, ids: list[int]) -> None:
        if not ids:
            return
        with self._conn() as c:
            c.executemany("UPDATE episodes SET status = ? WHERE id = ?",
                          [(status, i) for i in ids])

    def recent_episodes(self, namespace: str, n: int = 3) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM episodes WHERE namespace = ? ORDER BY ts DESC LIMIT ?",
                (namespace, n),
            ).fetchall()
            return [dict(r) for r in rows]

    def count_for_namespace(self, namespace: str) -> int:
        with self._conn() as c:
            row = c.execute("SELECT COUNT(*) AS n FROM episodes WHERE namespace = ?",
                            (namespace,)).fetchone()
            return int(row["n"])
