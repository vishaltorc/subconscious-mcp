"""tests/test_hookcli.py"""
from __future__ import annotations

import json
from pathlib import Path

from subconscious_mcp.hookcli import log_payload_sample


def test_log_payload_sample_writes_file(tmp_path: Path):
    payload = {"hook_event_name": "Stop", "session_id": "abc", "cwd": "/tmp/x"}
    out = log_payload_sample(payload, samples_dir=tmp_path)
    assert out.exists()
    assert json.loads(out.read_text())["hook_event_name"] == "Stop"


def test_log_payload_sample_never_raises(tmp_path: Path):
    # unwritable dir must not raise (hooks never break sessions)
    bad = tmp_path / "nope"
    bad.write_text("a file, not a dir")
    out = log_payload_sample({"x": 1}, samples_dir=bad)
    assert out is None
