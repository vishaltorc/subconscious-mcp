"""tests/test_hookcli.py"""
from __future__ import annotations

import json
from pathlib import Path

from subconscious_mcp.hookcli import (
    derive_namespace,
    extract_resolution_pair,
    handle_stop,
    log_payload_sample,
)
from subconscious_mcp.store import EpisodeStore


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


def test_derive_namespace_from_dir_name(tmp_path):
    proj = tmp_path / "My Cool-Project"
    proj.mkdir()
    assert derive_namespace(proj) == "my-cool-project"


def _write_transcript(path, lines):
    import json as j
    path.write_text("\n".join(j.dumps(x) for x in lines), encoding="utf-8")


def test_extract_resolution_pair(tmp_path):
    t = tmp_path / "t.jsonl"
    _write_transcript(t, [
        {"type": "user", "message": {"content": [{"type": "text", "text": "early"}]}},
        {"type": "user", "message": {"content": [{"type": "text", "text": "fix the deploy"}]}},
        {"type": "assistant",
         "message": {"content": [{"type": "text", "text": "ran vercel --prod, done"}]}},
    ])
    pair = extract_resolution_pair(t)
    assert pair == ("fix the deploy", "ran vercel --prod, done")


def test_extract_resolution_pair_handles_garbage(tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text("{not json\n\n", encoding="utf-8")
    assert extract_resolution_pair(t) is None


def test_handle_stop_writes_redacted_episode(tmp_path):
    t = tmp_path / "t.jsonl"
    _write_transcript(t, [
        {"type": "user", "message": {"content": [{"type": "text", "text": "set key"}]}},
        {"type": "assistant",
         "message": {"content": [{"type": "text", "text": "use sk-abc123DEF456ghi789jkl012"}]}},
    ])
    payload = {"hook_event_name": "Stop", "session_id": "s9",
               "transcript_path": str(t), "cwd": str(tmp_path)}
    rc = handle_stop(payload, db_path=tmp_path / "context.db", capture_enabled=True)
    assert rc == 0
    rows = EpisodeStore(tmp_path / "context.db").pending_episodes()
    assert len(rows) == 1
    assert "sk-abc" not in rows[0]["content"]
    assert "TASK: set key" in rows[0]["content"]


def test_handle_stop_capture_disabled_noop(tmp_path):
    rc = handle_stop({"cwd": str(tmp_path)}, db_path=tmp_path / "context.db", capture_enabled=False)
    assert rc == 0
    assert EpisodeStore(tmp_path / "context.db").pending_episodes() == []
