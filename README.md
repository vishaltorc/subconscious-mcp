# subconscious-mcp

A **local-first, learning, semantic memory layer** for any MCP-compatible LLM agent.

The server runs as an MCP `stdio` process on your machine and exposes four tools — `recall`, `remember`, `forget`, `stats` — that let an agent ask "have I seen this task before?" and, if so, get back the previous answer in milliseconds without re-running the work.

Embeddings come from `sentence-transformers/all-MiniLM-L6-v2` (384-dim, runs on CPU). Storage is a persistent local [ChromaDB](https://www.trychroma.com/) collection. No data leaves your machine.

---

## Install

```bash
# Once published:
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
    "subconscious": {
      "command": "subconscious-mcp",
      "args": []
    }
  }
}
```

If `subconscious-mcp` isn't on Claude Desktop's `PATH`, use the absolute path printed by `which subconscious-mcp`, e.g. `"command": "/Users/you/.local/bin/subconscious-mcp"`.

Then quit and restart Claude Desktop. The new tools appear under the 🔌 indicator.

### Claude Code

Option A — register from the CLI (recommended):

```bash
claude mcp add subconscious-mcp -- subconscious-mcp
```

Option B — edit `~/.claude.json` (or your project's `.mcp.json`) and add:

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

Reload the Claude Code session and the four tools become available.

A copy-pasteable file is in [`examples/claude_desktop_config.json`](examples/claude_desktop_config.json) and [`examples/claude_code_config.json`](examples/claude_code_config.json).

---

## Tools

### `recall(task, threshold=0.85, top_k=1)`

Semantic search for a previously remembered task.

| arg | type | default | meaning |
|---|---|---|---|
| `task` | str | — | the task description to look up |
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

On a miss, `hit` is `false`, `answer` is `null`, and `similarity` is the **best similarity observed in `top_k`** — so callers can see how close they came.

### `remember(task, answer, tags=[], ttl_seconds=null)`

Persist a `(task, answer)` pair. Returns `{stored, entry_id, embedding_dim}`.

`ttl_seconds=null` means never expire. Pass an integer to have the entry filtered out of future recalls after that many seconds.

### `forget(entry_id)`

Delete the entry with this id. Returns `{"forgotten": true}` if it existed, else `false`.

### `stats()`

Returns `{"total_entries", "last_hit_at", "hit_rate_last_100"}`. `hit_rate_last_100` is a sliding window over the most recent 100 recall calls — useful to see whether memory is actually paying off.

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
| `default_ttl_seconds` | `null` | — |
| `log_level` | `INFO` | `SUBCONSCIOUS_LOG_LEVEL` |

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
└── logs/server.log        rotating, 2MB x 3 backups
```

To wipe your memory: `rm -rf ~/.subconscious-mcp/data`.

---

## Demo session

See [`examples/demo_session.md`](examples/demo_session.md) for a worked example of an agent calling `recall` (miss → `remember`), then on a later turn calling `recall` again with a paraphrase and getting a hit.

---

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the layered design (server / tools / memory / config), the rationale behind ChromaDB + cosine similarity, and the TTL strategy.

---

## Troubleshooting

**`subconscious-mcp: command not found` after install**
Your shell's `PATH` doesn't include the install location. Try `python -m subconscious_mcp.server --help` to confirm the package works, then use the absolute path in your MCP client config.

**Claude Desktop says "Server disconnected"**
Check `~/.subconscious-mcp/logs/server.log` for the traceback. Most common causes:
1. The model download failed (offline at first launch) — re-run with network connectivity.
2. The `storage_dir` is on a read-only volume.

**First recall is slow**
The first invocation lazily loads the sentence-transformer model (~5s on a modest CPU). Subsequent calls reuse the loaded model and respond in milliseconds.

**Recall keeps missing on obvious paraphrases**
Lower the threshold (`recall(task=..., threshold=0.7)`) or raise `top_k` to see candidates. `all-MiniLM-L6-v2` is small and fast — for higher-quality matching set `SUBCONSCIOUS_EMBEDDING_MODEL=all-mpnet-base-v2`.

**Tests fail with a sentence-transformers download error**
You're offline or behind a proxy. Set `HF_HUB_OFFLINE=1` once you've pre-downloaded the model, or run `python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"` once with connectivity.

---

## License

MIT © 2026 Vishal Jayaprakash
