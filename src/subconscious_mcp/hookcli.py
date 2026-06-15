"""src/subconscious_mcp/hookcli.py

Claude Code hook-side entry points. HARD RULE: this module never imports
the embedding model, chromadb, or memory.py. Hooks must run in <100ms and
must never break a session: every public function swallows its errors.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from subconscious_mcp.naming import sanitize_namespace
from subconscious_mcp.redact import redact
from subconscious_mcp.store import EpisodeStore

_TAIL_BYTES = 256_000  # bounded transcript read


def log_payload_sample(payload: dict[str, Any], samples_dir: Path) -> Path | None:
    """Write one raw hook payload for schema calibration. Returns path or None."""
    try:
        samples_dir.mkdir(parents=True, exist_ok=True)
        name = (
            f"{int(time.time() * 1000)}_{os.getpid()}_"
            f"{payload.get('hook_event_name', 'unknown')}.json"
        )
        out = samples_dir / name
        out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return out
    except Exception:
        return None


def _git_root(cwd: Path) -> Path | None:
    try:
        out = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=True, timeout=2)
        return Path(out.stdout.strip())
    except Exception:
        return None


def derive_namespace(cwd: Path) -> str:
    root = _git_root(cwd) or cwd
    return sanitize_namespace(root.name)


def _log_failure(log_dir: Path, context: str, exc: Exception) -> None:
    """Append one line to hook.log. Itself swallows everything."""
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        line = f"{time.time():.3f} {context} {type(exc).__name__}: {exc}\n"
        with (log_dir / "hook.log").open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def _text_of(message: object) -> str | None:
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [b.get("text", "") for b in content
                     if isinstance(b, dict) and b.get("type") == "text"]
            joined = "\n".join(p for p in parts if p)
            return joined or None
    return None


def extract_resolution_pair(transcript_path: Path) -> tuple[str, str] | None:
    """Last (user text, following assistant text) pair from a bounded tail read.

    An assistant text only ever pairs with the most recent PRECEDING user
    text; a trailing unanswered user turn never steals an older outcome.
    """
    try:
        size = transcript_path.stat().st_size
        with transcript_path.open("rb") as f:
            if size > _TAIL_BYTES:
                f.seek(size - _TAIL_BYTES)
            raw = f.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    last_user: str | None = None
    pair: tuple[str, str] | None = None
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        text = _text_of(rec.get("message"))
        if not text:
            continue
        if rec.get("type") == "user":
            last_user = text
        elif rec.get("type") == "assistant" and last_user is not None:
            pair = (last_user, text)
    return pair


def handle_stop(payload: dict[str, Any], db_path: Path, capture_enabled: bool) -> int:
    """Capture one episode. Never raises; always returns 0."""
    try:
        if not capture_enabled:
            return 0
        cwd = Path(payload.get("cwd") or os.getcwd())
        tp = payload.get("transcript_path")
        if not tp:
            return 0
        pair = extract_resolution_pair(Path(tp))
        if pair is None:
            return 0
        task, answer = pair
        task_r = redact(task)[:1000]
        answer_r = redact(answer)[:2000]
        content = f"TASK: {task_r}\nOUTCOME: {answer_r}"
        EpisodeStore(db_path).add_episode(
            namespace=derive_namespace(cwd), project=str(cwd),
            session_id=str(payload.get("session_id", "")),
            content=content, source="stop_hook",
        )
    except Exception as exc:
        _log_failure(db_path.parent / "logs", "handle_stop", exc)
    return 0


def handle_session_start(payload: dict[str, Any], db_path: Path) -> int:
    """Print recent project context for Claude Code to absorb. Never raises."""
    try:
        cwd = Path(payload.get("cwd") or os.getcwd())
        ns = derive_namespace(cwd)
        store = EpisodeStore(db_path)
        recent = store.recent_episodes(namespace=ns, n=3)
        if not recent:
            return 0
        total = store.count_for_namespace(ns)
        lines = [f"## subconscious-mcp: recent context for this project ({ns})"]
        for ep in recent:
            lines.append(f"- {ep['content'][:400]}")
        lines.append(
            f"({total} stored episodes; subconscious-mcp memory is active. "
            "Call the recall tool before starting non-trivial work.)"
        )
        print("\n".join(lines))
    except Exception as exc:
        _log_failure(db_path.parent / "logs", "handle_session_start", exc)
    return 0


def run_hook_command(event: str) -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    from subconscious_mcp.config import load_config
    cfg = load_config()
    db_path = cfg.storage_path / "context.db"
    if event == "log-only":
        log_payload_sample(payload, cfg.storage_path / "logs" / "payload_samples")
        return 0
    if event == "stop":
        return handle_stop(payload, db_path=db_path, capture_enabled=cfg.capture_enabled)
    if event == "session-start":
        return handle_session_start(payload, db_path=db_path)
    return 0
