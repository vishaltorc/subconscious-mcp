# subconscious-mcp

[![CI](https://github.com/vishaltorc/subconscious-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/vishaltorc/subconscious-mcp/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/subconscious-mcp.svg)](https://pypi.org/project/subconscious-mcp/) [![Python](https://img.shields.io/pypi/pyversions/subconscious-mcp.svg)](https://pypi.org/project/subconscious-mcp/) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![MCP Registry](https://img.shields.io/badge/MCP%20Registry-active-blue)](https://registry.modelcontextprotocol.io/v0/servers?search=subconscious)

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

## Ambient memory

Beyond the explicit tools, subconscious-mcp can capture your work automatically through Claude Code hooks. Three commands get you there:

```bash
pip install subconscious-mcp
claude mcp add subconscious-mcp -- subconscious-mcp
subconscious-mcp install-hooks
```

`install-hooks` edits your Claude Code `settings.json` (default `~/.claude/settings.json`) to register two hooks: a `SessionStart` hook and a `Stop` hook. It backs up the existing file first (`settings.json.bak.<timestamp>`), writes atomically, and is idempotent: running it again when both hooks are already present is a no-op. Pass `--dry-run` to print the planned change without writing, and `--settings <path>` to target a different settings file.

What gets captured: when a session ends, the `Stop` hook reads the tail of the transcript, extracts the last user-request to assistant-outcome exchange, redacts secrets (best effort, see [Privacy](#privacy)), and writes one episode per session into `~/.subconscious-mcp/data/context.db` (a plain SQLite inbox). The hooks never load the embedding model or ChromaDB; the MCP server embeds and ingests pending episodes at its next startup.

What `SessionStart` injects: at the start of a session it prints this project's most recent episodes (up to 3) plus a one-line nudge to call `recall` before starting non-trivial work. Claude Code absorbs that text as context.

Capture is per-project automatically. The namespace is derived from the git repository root folder name (falling back to the current directory basename), so each project's episodes and curated memory stay isolated without any configuration. Set `namespace` explicitly in config to override.

---

## Privacy

Everything stays on your machine. Episodes captured by the ambient hooks live in `~/.subconscious-mcp/data/context.db`, a plain SQLite file you can inspect with any SQL client:

```bash
sqlite3 ~/.subconscious-mcp/data/context.db 'SELECT ts, namespace, substr(content,1,80) FROM episodes ORDER BY ts DESC LIMIT 10'
```

Before an episode is written, the captured text passes through a best-effort redactor. It currently masks these shapes:

- OpenAI / Anthropic `sk-` keys (including `sk-ant-`, `sk-proj-`)
- PyPI tokens (`pypi-`)
- GitHub classic tokens (`ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`) and fine-grained tokens (`github_pat_`)
- Slack tokens (`xoxb-`, `xoxa-`, `xoxp-`, `xoxr-`, `xoxs-`)
- AWS access key ids (`AKIA...`)
- `Bearer` authorization tokens
- PEM private key headers (`-----BEGIN ... PRIVATE KEY-----`)
- `KEY=value` env assignments where the name ends in `KEY` / `TOKEN` / `SECRET` / `PASSWORD` / `PASSWD` (the value is masked, the name is kept)

Redaction is best effort, not a guarantee. Known gaps it does NOT catch: AWS secret access keys (bare 40-char strings), bare JWTs outside a `Bearer` prefix, passwords inside connection strings (`postgres://user:pass@host`), Stripe secret keys (`sk_live_` / `sk_test_`, underscore form), and npm tokens. Treat capture as a convenience, not a vault.

To turn capture off entirely, set `capture_enabled=false` in config or `SUBCONSCIOUS_CAPTURE_ENABLED=false` in the environment. The `Stop` hook then captures nothing.

To wipe everything subconscious-mcp has stored (curated memory, episodes, echo logs, server logs) in one line:

```bash
rm -rf ~/.subconscious-mcp
```

---

## Tools

### `recall(task, threshold=0.85, top_k=1)`

Semantic search for a previously remembered task.

| arg | type | default | meaning |
|---|---|---|---|
| `task` | str | (required) | the task description to look up |
| `threshold` | float | 0.85 | minimum cosine similarity for a hit |
| `top_k` | int | 1 | how many candidates to consider |
| `tags` | list[str] | null | optional; candidate must share at least one |

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

When `tags` is supplied, the miss `similarity` reflects the best match within the fetched window intersected with the tag filter, and can be `0.0` even when a tag-matching entry exists beyond the window (raise `top_k` to widen the window).

### `remember(task, answer, tags=[], ttl_seconds=null, skip_if_duplicate=false)`

Persist a `(task, answer)` pair. Returns `{stored, entry_id, embedding_dim}`.

`ttl_seconds=null` means never expire. Pass an integer to have the entry filtered out of future recalls after that many seconds.

Before storing, the nearest curated entry is probed. If its cosine similarity falls in the near-duplicate band `[0.75, 0.92]`, the result also carries `warning="near_duplicate"` with `nearest_task`, `nearest_similarity`, and `nearest_entry_id` (a write-time first-fill drift guard that complements `drift_report`). The entry is still stored. Pass `skip_if_duplicate=true` to skip the write instead, in which case the result is `{stored: false, ...}` with the same warning fields. Ambient capture episodes never trigger the warning.

The band `[0.75, 0.92]` is deliberately independent of `default_threshold` (0.85), so it straddles the recall threshold: the warning fires on neighbours that recall might or might not return. Similarities above 0.92 are treated as update-territory (basically the same task) and are intentionally not warned. To act on a warning, `recall` the `nearest_entry_id` (or look it up) to inspect the existing entry, then decide whether to merge, update, or proceed.

### `echo(task, top_k=5)`

Sonar ping: return the nearest non-expired entries **without their answers**.

| arg | type | default | meaning |
|---|---|---|---|
| `task` | str | (required) | the task description to ping with |
| `top_k` | int | 5 | how many nearest entries to report |
| `tags` | list[str] | null | optional; candidate must share at least one |

Returns:

```json
{
  "count": 47,
  "echoes": [
    {"entry_id": "uuid", "similarity": 0.91, "task_text": "...", "stored_at": 1731000000.0, "tags": ["..."], "kind": "memory"}
  ]
}
```

Use it to sense whether a task sits in known territory before committing to a recall. Because no answer is returned, an echo can never propagate a stale or wrong cached answer. Echo calls don't count toward the hit rate and aren't written to the echo log.

Each echo carries a `kind`: `"memory"` for curated `remember` entries, `"episode"` for ingested ambient capture. Episodes surface in `echo` but never in `recall` answers.

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
| `namespace` | `default` | `SUBCONSCIOUS_NAMESPACE` |
| `capture_enabled` | `true` | `SUBCONSCIOUS_CAPTURE_ENABLED` |

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
│   ├── echo_log.jsonl     one line per recall: query, nearest entry, similarity, hit
│   └── context.db         SQLite inbox for ambient-capture episodes (shared across namespaces)
└── logs/server.log        rotating, 2MB x 3 backups
```

The tree above is the default namespace. With a non-default `namespace`, the echo log is named `echo_log_{namespace}.jsonl` instead, while `context.db` is shared across namespaces (each episode carries its own `namespace` column).

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
