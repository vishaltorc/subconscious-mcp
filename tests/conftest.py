"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from subconscious_mcp.config import Config
from subconscious_mcp.memory import Memory


@pytest.fixture
def config(tmp_path: Path) -> Config:
    """A config pointing storage into a temp dir so tests are hermetic."""
    return Config(
        storage_dir=str(tmp_path / "data"),
        embedding_model="all-MiniLM-L6-v2",
        default_threshold=0.85,
        default_ttl_seconds=None,
        log_level="WARNING",
    )


@pytest.fixture
def memory(config: Config) -> Memory:
    return Memory(config)
