"""src/subconscious_mcp/hookcli.py

Claude Code hook-side entry points. HARD RULE: this module never imports
the embedding model, chromadb, or memory.py. Hooks must run in <100ms and
must never break a session: every public function swallows its errors.
"""
from __future__ import annotations

import json
import time
from pathlib import Path


def log_payload_sample(payload: dict, samples_dir: Path) -> Path | None:
    """Write one raw hook payload for schema calibration. Returns path or None."""
    try:
        samples_dir.mkdir(parents=True, exist_ok=True)
        name = f"{int(time.time() * 1000)}_{payload.get('hook_event_name', 'unknown')}.json"
        out = samples_dir / name
        out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return out
    except Exception:
        return None
