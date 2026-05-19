"""Configuration loading for subconscious-mcp.

Priority (highest wins): environment variables > ~/.subconscious-mcp/config.json > defaults.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


DEFAULT_CONFIG_PATH = Path.home() / ".subconscious-mcp" / "config.json"


class Config(BaseModel):
    """Runtime configuration for the server."""

    model_config = {"validate_default": True}

    storage_dir: str = Field(default="~/.subconscious-mcp/data")
    embedding_model: str = Field(default="all-MiniLM-L6-v2")
    default_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    default_ttl_seconds: int | None = Field(default=None)
    log_level: str = Field(default="INFO")

    @field_validator("storage_dir")
    @classmethod
    def _expand(cls, v: str) -> str:
        return str(Path(os.path.expanduser(v)).resolve())

    @field_validator("log_level")
    @classmethod
    def _upper(cls, v: str) -> str:
        v = v.upper()
        if v not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"invalid log_level: {v}")
        return v

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_dir)

    @property
    def log_path(self) -> Path:
        return Path.home() / ".subconscious-mcp" / "logs" / "server.log"


def _load_from_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise RuntimeError(f"config file {path} is not valid JSON: {e}") from e


def _load_from_env() -> dict[str, Any]:
    """Read SUBCONSCIOUS_* env vars; only override keys actually present."""
    out: dict[str, Any] = {}
    if v := os.getenv("SUBCONSCIOUS_STORAGE_DIR"):
        out["storage_dir"] = v
    if v := os.getenv("SUBCONSCIOUS_EMBEDDING_MODEL"):
        out["embedding_model"] = v
    if v := os.getenv("SUBCONSCIOUS_DEFAULT_THRESHOLD"):
        try:
            out["default_threshold"] = float(v)
        except ValueError as e:
            raise RuntimeError(f"SUBCONSCIOUS_DEFAULT_THRESHOLD must be a float: {v}") from e
    if v := os.getenv("SUBCONSCIOUS_LOG_LEVEL"):
        out["log_level"] = v
    return out


def load_config(config_path: Path | None = None) -> Config:
    """Merge defaults <- json file <- env, then validate."""
    path = config_path if config_path is not None else DEFAULT_CONFIG_PATH
    merged: dict[str, Any] = {}
    merged.update(_load_from_file(path))
    merged.update(_load_from_env())
    return Config(**merged)
