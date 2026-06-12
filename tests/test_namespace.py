"""tests/test_namespace.py"""
from __future__ import annotations

from subconscious_mcp.config import Config, sanitize_namespace


def test_sanitize_namespace_basic():
    assert sanitize_namespace("my-project") == "my-project"
    # space/! become -, then trailing punctuation stripped
    assert sanitize_namespace("My Project!") == "my-project"
    # ASCII only; chromadb rejects unicode names
    assert sanitize_namespace("café") == "caf"
    assert sanitize_namespace("") == "default"
    assert sanitize_namespace("x" * 100) == "x" * 64


def test_sanitized_names_accepted_by_chromadb(tmp_path):
    import chromadb
    client = chromadb.PersistentClient(path=str(tmp_path))
    for hostile in ["My Project!", "café", "---", "x" * 100, "über-app!!"]:
        name = f"subconscious_{sanitize_namespace(hostile)}"
        client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


def test_config_namespace_default():
    c = Config(storage_dir="/tmp/t")
    assert c.namespace == "default"


def test_config_namespace_sanitized():
    c = Config(storage_dir="/tmp/t", namespace="My Repo")
    assert c.namespace == "my-repo"


def test_config_namespace_env(monkeypatch):
    from subconscious_mcp.config import load_config
    monkeypatch.setenv("SUBCONSCIOUS_NAMESPACE", "proj-a")
    monkeypatch.setenv("SUBCONSCIOUS_STORAGE_DIR", "/tmp/t2")
    c = load_config()
    assert c.namespace == "proj-a"


def test_config_capture_enabled_env(monkeypatch):
    from subconscious_mcp.config import load_config
    monkeypatch.setenv("SUBCONSCIOUS_CAPTURE_ENABLED", "false")
    c = load_config()
    assert c.capture_enabled is False
