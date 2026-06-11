"""subconscious-mcp server entry point.

Exposes six MCP tools over stdio:

  - recall(task, threshold, top_k)
  - remember(task, answer, tags, ttl_seconds)
  - echo(task, top_k)
  - drift_report(min_hits, min_spread)
  - forget(entry_id)
  - stats()

stdout is reserved for JSON-RPC. All logs go to ~/.subconscious-mcp/logs/server.log.
"""

from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import __version__
from .config import Config, load_config
from .memory import Memory
from .tools import register_tools


def _build_server(config: Config):
    """Create a FastMCP instance and register every tool against the supplied config."""
    from mcp.server.fastmcp import FastMCP  # imported here so --help stays cheap

    mcp = FastMCP("subconscious-mcp")
    # FastMCP in mcp 1.27.1 has no version kwarg; Server.version is the public
    # field create_initialization_options() reads. Move into the constructor
    # once the SDK exposes it.
    mcp._mcp_server.version = __version__
    memory = Memory(config)
    register_tools(mcp, memory)
    return mcp, memory


def _setup_logging(config: Config) -> None:
    """Route logs to a rotating file. Never touch stdout (MCP owns it)."""
    log_path = config.log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.setLevel(getattr(logging, config.log_level))
    # purge any default handlers (avoid stdout leakage during tests/launchers)
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="subconscious-mcp",
        description=(
            "A local-first semantic memory MCP server. Exposes recall / remember / "
            "echo / drift_report / forget / stats tools over stdio for any "
            "MCP-compatible client (Claude Desktop, Claude Code, etc.)."
        ),
        epilog=(
            "Configuration is loaded in priority order:\n"
            "  1. Environment vars (SUBCONSCIOUS_STORAGE_DIR, "
            "SUBCONSCIOUS_EMBEDDING_MODEL,\n"
            "     SUBCONSCIOUS_DEFAULT_THRESHOLD, SUBCONSCIOUS_LOG_LEVEL)\n"
            "  2. ~/.subconscious-mcp/config.json\n"
            "  3. Built-in defaults\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"subconscious-mcp {__version__}"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a JSON config file (default: ~/.subconscious-mcp/config.json).",
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print the resolved configuration to stderr and exit (does not start the server).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    config = load_config(args.config)
    _setup_logging(config)
    log = logging.getLogger(__name__)
    log.info("subconscious-mcp v%s starting; storage=%s", __version__, config.storage_dir)

    if args.print_config:
        print(config.model_dump_json(indent=2), file=sys.stderr)
        return 0

    mcp, _ = _build_server(config)
    try:
        # FastMCP.run() defaults to stdio transport, which is what every
        # local MCP client (Claude Desktop, Claude Code) expects.
        mcp.run()
    except KeyboardInterrupt:
        log.info("interrupted; shutting down")
        return 0
    except Exception:
        log.exception("server crashed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
