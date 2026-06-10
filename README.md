# subconscious-mcp

[![PyPI](https://img.shields.io/pypi/v/subconscious-mcp.svg)](https://pypi.org/project/subconscious-mcp/) [![Python](https://img.shields.io/pypi/pyversions/subconscious-mcp.svg)](https://pypi.org/project/subconscious-mcp/) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![MCP Registry](https://img.shields.io/badge/MCP%20Registry-active-blue)](https://registry.modelcontextprotocol.io/v0/servers?search=subconscious)

Local-first semantic memory for MCP agents. Recall, remember, forget, echo, drift detection, stats over stdio.

The server runs as an MCP stdio process on your machine. It exposes six tools that let an agent ask "have I seen this task before?" and, if so, get the previous answer back in milliseconds without re-running the work. Inspired by bat echolocation: even a recall miss reports how close the nearest memory was, an `echo` tool senses nearby memories without retrieving answers, and every recall outcome is logged so `drift_report` can flag cached answers that are absorbing too broad a family of queries (first-fill semantic drift).

Embeddings come from sentence-transformers/all-MiniLM-L6-v2 (384-dim, runs on CPU). Storage is a persistent local ChromaDB collection. No data leaves your machine.

<!-- mcp-name: io.github.vishaltorc/subconscious-mcp -->

---

## Install

```bash
# From PyPI:
pip install subconscious-mcp

# Local development:
git clone https://github.com/vishaltorc/subconscious-mcp
cd subconscious-mcp
pip install -e ".[dev]"
```

After install you can run the server from anywhere:

```bash
subconscious-mcp --help
```

The first time a tool is called, the embedding model (~80MB) is downloaded into the local Hugging Face cache. Subsequent starts are fast.

---

## Configure your MCP client

### Claude Desktop

Edit your config file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Add an `mcpServers` entry:

```json
{
  "mcpServers": {
    "subconscious-mcp": {
      "command": "subconscious-mcp",
      "args": []
    }
  }
}
```

If `subconscious-mcp` isn't on Claude Desktop's `PATH`, use the absolute path printed by `which subconscious-mcp`, e.g. `"command": "/Users/you/.local/bin/subconscious-mcp"`.

Then quit and restart Claude Desktop. The new tools appear under the 🔌 indicator.

### Claude Code

Option A. Register from the CLI (recommended):

```bash
claude mcp add subconscious-mcp -- subconscious-mcp
```

Option B. Edit `~/.claude.json` (or your project's `.mcp.json`) and add:

```json
{
  "mcpServers": {
    "subconscious-mcp": {
      "command": "subconscious-mcp",
      "args": [],
      "type": "stdio"
    }
  }
}
```

Reload the Claude Code session and the six tools become available.

A copy-pasteable file is in [`examples/claude_desktop_config.json`](examples/claude_desktop_config.json) and [`examples/claude_code_config.json`](examples/claude_code_config.json).

---

## Tools

### `recall(task, threshold=0.85, top_k=1)`

Semantic search for a previously remembered task.

| arg | type | default | meaning |
|---|---|---|---|
| `task` | str | (required) | the task description to look up |
| `threshold` | float | 0.85 | minimum cosine similarity for a hit |
| `top_k` | int | 1 | how many candidates to consider |

Returns:

```json
{
  "hit": true,
  "similarity": 0.91,
  "answer": "...",
  "task_text": "...",
  "entry_id": "uuid",
  "stored_at": 1731000000.0,
  "tags": ["..."]
}
```

On a miss, `hit` is `false`, `answer` is `null`, and `similarity` is the **best similarity observed in `top_k`**. Callers can see how close they came.

### `remember(task, answer, tags=[], ttl_seconds=null)`

Persist a `(task, answer)` pair. Returns `{stored, entry_id, embedding_dim}`.

`ttl_seconds=null` means never expire. Pass an integer to have the entry filtered out of future recalls after that many seconds.

### `echo(task, top_k=5)`

Sonar ping: return the nearest non-expired entries **without their answers**.

| arg | type | default | meaning |
|---|---|---|---|
| `task` | str | (required) | the task description to ping with |
| `top_k` | int | 5 | how many nearest entries to report |

Returns:

```json
{
  "count": 47,
  "echoes": [
    {"entry_id": "uuid", "similarity": 0.91, "task_text": "...", "stored_at": 1731000000.0, "tags": ["..."]}
  ]
}
```

Use it to sense whether a task sits in known territory before committing to a recall. Because no answer is returned, an echo can never propagate a stale or wrong cached answer. Echo calls don't count toward the hit rate and aren't written to the echo log.

### `drift_report(min_hits=3, min_spread=0.08)`

Analyze the echo log for **first-fill semantic drift** candidates: entries whose recall hits span a wide similarity band across distinct query phrasings. A wide band means one cached answer is absorbing a broad family of queries that may carry subtly different interpretations (see [`validation/results.md`](validation/results.md) for the failure mode this detects).

| arg | type | default | meaning |
|---|---|---|---|
| `min_hits` | int | 3 | minimum recorded hits before an entry is considered |
| `min_spread` | float | 0.08 | minimum (max - min) hit-similarity band to flag |

Returns:

```json
{
  "analyzed_recalls": 412,
  "entries_with_hits": 38,
  "candidates": [
    {
      "entry_id": "uuid",
      "task_text": "Pull out all digits...",
      "still_stored": true,
      "hits": 5,
      "distinct_queries": 4,
      "similarity_min": 0.82,
      "similarity_max": 0.94,
      "similarity_spread": 0.12
    }
  ]
}
```

Flagged entries are review candidates: `forget` them, split them into more specific entries, or raise the recall threshold for that family.

### `forget(entry_id)`

Delete the entry with this id. Returns `{"forgotten": true}` if it existed, else `false`.

### `stats()`

Returns `{"total_entries", "last_hit_at", "hit_rate_last_100"}`. `hit_rate_last_100` is a sliding window over the most recent 100 recall calls. Useful to see whether memory is actually paying off.

---

## Configuration

Configuration is resolved in priority order:

1. Environment variables (highest)
2. `~/.subconscious-mcp/config.json`
3. Built-in defaults

| key | default | env var |
|---|---|---|
| `storage_dir` | `~/.subconscious-mcp/data` | `SUBCONSCIOUS_STORAGE_DIR` |
| `embedding_model` | `all-MiniLM-L6-v2` | `SUBCONSCIOUS_EMBEDDING_MODEL` |
| `default_threshold` | `0.85` | `SUBCONSCIOUS_DEFAULT_THRESHOLD` |
| `default_ttl_seconds` | `null` |  |
| `log_level` | `INFO` | `SUBCONSCIOUS_LOG_LEVEL` |
| `echo_log_enabled` | `true` | `SUBCONSCIOUS_ECHO_LOG_ENABLED` |
| `echo_log_max_bytes` | `5000000` | `SUBCONSCIOUS_ECHO_LOG_MAX_BYTES` |

Inspect the resolved config without starting the server:

```bash
subconscious-mcp --print-config
```

---

## Files written on disk

```
~/.subconscious-mcp/
├── config.json            (optional, user-edited)
├── data/                  ChromaDB collection (sqlite + parquet)
│   └── echo_log.jsonl     one line per recall: query, nearest entry, similarity, hit
└── logs/server.log        rotating, 2MB x 3 backups
```

The echo log self-compacts: when it exceeds `echo_log_max_bytes` (5MB default), the oldest half is dropped. Set `SUBCONSCIOUS_ECHO_LOG_ENABLED=0` to disable it entirely (this also disables `drift_report`).

To wipe your memory (including the echo log): `rm -rf ~/.subconscious-mcp/data`.

---

## Demo session

See [`examples/demo_session.md`](examples/demo_session.md) for a worked example of an agent calling `recall` (miss, then `remember`), then on a later turn calling `recall` again with a paraphrase and getting a hit.

---

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the layered design (server / tools / memory / config), the rationale behind ChromaDB + cosine similarity, and the TTL strategy.

---

## Troubleshooting

**`subconscious-mcp: command not found` after install**
Your shell's `PATH` doesn't include the install location. Try `python -m subconscious_mcp.server --help` to confirm the package works, then use the absolute path in your MCP client config.

**Claude Desktop says "Server disconnected"**
Check `~/.subconscious-mcp/logs/server.log` for the traceback. Most common causes:
1. The model download failed (offline at first launch). Re-run with network connectivity.
2. The `storage_dir` is on a read-only volume.

**First recall is slow**
The first invocation lazily loads the sentence-transformer model (~5s on a modest CPU). Subsequent calls reuse the loaded model and respond in milliseconds.

**`drift_report` returns no candidates**
Either too few recalls have been logged (each candidate needs `min_hits` hits from at least two distinct phrasings), or the echo log is disabled (`SUBCONSCIOUS_ECHO_LOG_ENABLED=0`). Check that `~/.subconscious-mcp/data/echo_log.jsonl` exists and is growing.

**Recall keeps missing on obvious paraphrases**
Lower the threshold (`recall(task=..., threshold=0.7)`) or raise `top_k` to see candidates. `all-MiniLM-L6-v2` is small and fast. For higher-quality matching set `SUBCONSCIOUS_EMBEDDING_MODEL=all-mpnet-base-v2`.

**Tests fail with a sentence-transformers download error**
You're offline or behind a proxy. Set `HF_HUB_OFFLINE=1` once you've pre-downloaded the model, or run `python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"` once with connectivity.

---

## License

MIT © 2026 Vishal Jayaprakash
