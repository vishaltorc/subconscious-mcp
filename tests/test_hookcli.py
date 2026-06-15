"""tests/test_hookcli.py"""
from __future__ import annotations

import json
from pathlib import Path

from subconscious_mcp.hookcli import (
    derive_namespace,
    extract_resolution_pair,
    handle_session_start,
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


def test_derive_namespace_from_dir_name(tmp_path, monkeypatch):
    monkeypatch.setattr("subconscious_mcp.hookcli._git_root", lambda cwd: None)
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
    assert not (tmp_path / "context.db").exists()
    assert EpisodeStore(tmp_path / "context.db").pending_episodes() == []


def test_extract_resolution_pair_skips_non_dict_lines(tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text('"just a string"\n[1, 2]\n'
                 '{"type": "user", "message": {"content": [{"type": "text", "text": "u"}]}}\n'
                 '{"type": "assistant", "message": {"content": [{"type": "text", "text": "a"}]}}\n',
                 encoding="utf-8")
    assert extract_resolution_pair(t) == ("u", "a")


def test_extract_resolution_pair_never_cross_pairs(tmp_path):
    t = tmp_path / "t.jsonl"
    _write_transcript(t, [
        {"type": "user", "message": {"content": [{"type": "text", "text": "old task"}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "old answer"}]}},
        {"type": "user", "message": {"content": [{"type": "text", "text": "NEW task"}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "x"}]}},
    ])
    assert extract_resolution_pair(t) == ("old task", "old answer")


def test_extract_resolution_pair_tail_seek_partial_line(tmp_path):
    import json as j
    t = tmp_path / "big.jsonl"
    filler = {"type": "user", "message": {"content": [{"type": "text", "text": "x" * 1000}]}}
    lines = [j.dumps(filler)] * 300  # > 256KB of filler
    lines.append(j.dumps(
        {"type": "user", "message": {"content": [{"type": "text", "text": "final task"}]}}))
    lines.append(j.dumps(
        {"type": "assistant",
         "message": {"content": [{"type": "text", "text": "final answer"}]}}))
    t.write_text("\n".join(lines), encoding="utf-8")
    assert t.stat().st_size > 256_000
    assert extract_resolution_pair(t) == ("final task", "final answer")


def test_handle_stop_failure_writes_hook_log(tmp_path, monkeypatch):
    from subconscious_mcp import hookcli

    def boom(self, **kwargs):
        raise RuntimeError("forced store failure")

    monkeypatch.setattr(hookcli.EpisodeStore, "add_episode", boom)
    t = tmp_path / "t.jsonl"
    _write_transcript(t, [
        {"type": "user", "message": {"content": [{"type": "text", "text": "u"}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "a"}]}},
    ])
    payload = {"transcript_path": str(t), "cwd": str(tmp_path), "session_id": "s"}
    rc = hookcli.handle_stop(payload, db_path=tmp_path / "context.db", capture_enabled=True)
    assert rc == 0
    log = (tmp_path / "logs" / "hook.log").read_text()
    assert "handle_stop" in log and "forced store failure" in log


def test_redaction_happens_before_truncation(tmp_path):
    t = tmp_path / "t.jsonl"
    secret = "sk-" + "a" * 40
    long_prefix = "y" * 1995          # puts the secret across the old 2000-char cut
    _write_transcript(t, [
        {"type": "user", "message": {"content": [{"type": "text", "text": "u"}]}},
        {"type": "assistant",
         "message": {"content": [{"type": "text", "text": long_prefix + " " + secret}]}},
    ])
    payload = {"transcript_path": str(t), "cwd": str(tmp_path), "session_id": "s"}
    handle_stop(payload, db_path=tmp_path / "context.db", capture_enabled=True)
    rows = EpisodeStore(tmp_path / "context.db").pending_episodes()
    assert "sk-a" not in rows[0]["content"]


def test_session_start_prints_recent_context(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("subconscious_mcp.hookcli._git_root", lambda cwd: None)
    db = tmp_path / "context.db"
    proj = tmp_path / "projx"
    proj.mkdir()
    ns = derive_namespace(proj)
    EpisodeStore(db).add_episode(namespace=ns, project=str(proj), session_id="s1",
                                 content="TASK: a\nOUTCOME: b", source="stop_hook")
    rc = handle_session_start({"cwd": str(proj)}, db_path=db)
    out = capsys.readouterr().out
    assert rc == 0
    assert "TASK: a" in out
    assert "1 stored" in out


def test_session_start_empty_namespace_silent(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("subconscious_mcp.hookcli._git_root", lambda cwd: None)
    proj = tmp_path / "fresh"
    proj.mkdir()
    rc = handle_session_start({"cwd": str(proj)}, db_path=tmp_path / "context.db")
    assert rc == 0
    assert capsys.readouterr().out == ""
