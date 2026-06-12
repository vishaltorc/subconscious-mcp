"""src/subconscious_mcp/hookcli.py

Claude Code hook-side entry points. HARD RULE: this module never imports
the embedding model, chromadb, or memory.py. Hooks must run in <100ms and
must never break a session: every public function swallows its errors.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

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
    from subconscious_mcp.config import sanitize_namespace
    root = _git_root(cwd) or cwd
    return sanitize_namespace(root.name)


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
    """Last user text + last assistant text from a bounded tail read."""
    try:
        size = transcript_path.stat().st_size
        with transcript_path.open("rb") as f:
            if size > _TAIL_BYTES:
                f.seek(size - _TAIL_BYTES)
            raw = f.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    last_user = last_assistant = None
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = _text_of(rec.get("message"))
        if not text:
            continue
        if rec.get("type") == "user":
            last_user = text
        elif rec.get("type") == "assistant":
            last_assistant = text
    if last_user and last_assistant:
        return (last_user, last_assistant)
    return None


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
        content = redact(f"TASK: {task[:1000]}\nOUTCOME: {answer[:2000]}")
        EpisodeStore(db_path).add_episode(
            namespace=derive_namespace(cwd), project=str(cwd),
            session_id=str(payload.get("session_id", "")),
            content=content, source="stop_hook",
        )
    except Exception:
        pass
    return 0
