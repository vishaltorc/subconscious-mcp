# Architecture

`subconscious-mcp` is intentionally small: six MCP tools, one embedding model,
one persistent vector collection, one append-only echo log. This document
describes the layers, how data flows through them, and the design decisions
that shaped each one.

## Layered design

```
┌──────────────────────────────────────────┐
│  MCP client (Claude Desktop / Code)      │
│  speaks JSON-RPC over stdio              │
└──────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────┐
│  server.py     CLI + logging + FastMCP   │
└──────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────┐
│  tools.py      6 thin @mcp.tool() shims  │
└──────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────┐
│  memory.py    embed / store / query      │
│   - sentence-transformers (lazy)         │
│   - ChromaDB persistent collection       │
│   - in-memory ring buffer for stats      │
│   - echo log (JSONL) + drift detection   │
└──────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────┐
│  config.py    env > json > defaults      │
└──────────────────────────────────────────┘
```

Each layer is independently testable. The tests exercise `memory.py`
directly with no MCP transport, and `tools.py` via a tiny fake `FastMCP`
that captures the `@mcp.tool()` registrations.

## Data flow: `recall`

1. MCP client emits a JSON-RPC `tools/call` frame on stdin.
2. FastMCP routes it to the registered `recall` function in `tools.py`.
3. `tools.py` forwards to `Memory.recall(...)`.
4. `Memory` encodes the task with sentence-transformers (lazy first load).
5. `Memory` queries ChromaDB for the top-k nearest neighbours (cosine).
6. Expired entries (where `expires_at <= now`) are filtered out.
7. If the best non-expired similarity ≥ threshold → hit; else miss.
8. The outcome (query, nearest entry id, similarity, hit/miss, threshold)
   is appended to the echo log; failures here never break the recall.
9. Result is appended to the recent-calls ring buffer (for `stats`).
10. FastMCP serializes the dict and writes it back on stdout.

## Echolocation: `echo`, the echo log, and `drift_report`

The design borrows from bat sonar: send a ping, learn from the reflection,
and learn as much from the *shape* of many reflections as from any single one.

### `echo`: geometry without content

`echo(task, top_k)` embeds the task and returns the nearest non-expired
entries with their similarities, **but not their answers**. It is a pure
sensing operation:

- It cannot propagate a stale or wrong cached answer (it returns geometry,
  not content), so it is always safe to call.
- It does not touch the hit-rate ring buffer or the echo log; sensing is
  free of side effects on the metrics that recall maintains.
- An agent can ping before recalling: a strong echo (0.8+) suggests recall
  will pay off; silence (< 0.3) says this is uncharted territory.

### The echo log: every reflection, recorded

Every `recall` appends one JSONL line to `<storage_dir>/echo_log.jsonl`:
timestamp, query text, nearest entry id (even on a miss), best similarity,
hit/miss, and the threshold used. Design constraints:

- **Never break recall**: the write is wrapped so any logging failure is
  swallowed and logged to the server log instead.
- **Bounded size**: when the file exceeds `echo_log_max_bytes` (5MB
  default) the oldest half is dropped, atomically via a temp file +
  `os.replace`. JSONL means a torn line at worst corrupts one record, and
  the reader skips unparseable lines.
- **Local-first**: the log stays inside `storage_dir` and is wiped by the
  same `rm -rf` that wipes the collection.

### `drift_report`: detecting first-fill semantic drift

The validation study (`validation/results.md`) surfaced a failure mode
named first-fill semantic drift: the first answer cached for a family of
similar queries silently serves the whole family, even when later queries
carry a different interpretation ("digits" vs "numbers").

The acoustic signature of that failure lives in the echo log: an entry
being hit at similarities spanning a wide band (say 0.82 to 0.94) by
distinct query phrasings is one answer absorbing a suspiciously broad
family. `drift_report(min_hits, min_spread)` groups logged hits by entry,
computes each entry's hit-similarity band, and flags entries where:

- hits ≥ `min_hits` (default 3),
- band spread ≥ `min_spread` (default 0.08), and
- at least two distinct query phrasings were involved.

This detects drift candidates **before** any answer is verified wrong and
with zero extra LLM or embedding calls; the data is a by-product of normal
operation. Flagged entries are review candidates: `forget` them, split
them into more specific entries, or tighten the threshold.

## Ambient capture

v0.3 adds optional ambient capture through Claude Code hooks. The design is
shaped by one boundary: **the SQLite inbox**.

### The inbox boundary

```
┌────────────────────┐   write only    ┌──────────────┐
│  Stop hook         │ ──────────────► │              │
│  (separate process)│                 │  context.db  │
└────────────────────┘                 │  (SQLite)    │
┌────────────────────┐   read recent   │   inbox      │
│  SessionStart hook │ ◄────────────── │              │
│  (separate process)│                 └──────────────┘
└────────────────────┘                        │ ingest at startup
                                               ▼
                                        ┌──────────────┐
                                        │  MCP server  │
                                        │  (ChromaDB)  │
                                        └──────────────┘
```

Hooks are separate, short-lived processes spawned by Claude Code. They write
ONLY to `context.db` via `EpisodeStore` (`store.py`), which is the single
module that touches that file. The MCP server is the ONLY ChromaDB writer:
at startup it calls `ingest_pending()`, embeds each pending episode, adds it
to the collection, and marks it ingested in the inbox.

Why the split:

- **ChromaDB has no multi-writer story.** Two processes writing the same
  persistent collection risk index corruption. Funneling every write through
  one process (the server) sidesteps that entirely; the inbox is the
  hand-off.
- **Hooks must stay model-free and fast.** `hookcli.py` never imports
  sentence-transformers, ChromaDB, or `memory.py`. A hook reads a bounded
  tail of the transcript, redacts, and inserts one SQLite row, all well
  inside the <100ms budget a `Stop` hook should respect. Embedding (slow,
  heavy) is deferred to the server.

### Episode segregation

Ingested episodes are tagged `kind=episode` in their ChromaDB metadata.
`recall` skips any `kind=episode` row, so mechanically captured episodes
never appear in recall answers and cannot degrade the validated recall
accuracy (~95% in the validation study), which is measured over curated
`remember` entries only. Episodes are still visible to `echo` (each echo
carries its `kind`) and surface in the `SessionStart` context dump, so the
captured signal is available for sensing and orientation without polluting
the answer path. (`stats().total_entries` counts episodes too, since it
reports the raw collection size.)

### Write-time near-duplicate guard

`remember` probes the nearest curated neighbour before storing and warns when
its similarity falls in the band `[0.75, 0.92]` (`NEAR_DUPLICATE_LOW`,
`NEAR_DUPLICATE_HIGH` in `memory.py`). This is the write-time complement to
the read-time `drift_report`: drift is caught either as it is recorded
(write) or as it accumulates in the echo log (read). The probe ignores
`kind=episode` rows, so ambient capture never triggers a curated-duplicate
warning.

## Why these choices

### ChromaDB
- **Local-first**: persistent SQLite + parquet, no daemon, no network.
- **Decent ANN**: HNSW index, sub-millisecond lookups for tens of thousands of entries.
- **Metadata you can query**: lets us store `expires_at`, `tags_json`, etc. alongside vectors.

### `all-MiniLM-L6-v2`
- Small (~80MB), fast on CPU, 384-dim vectors.
- Trained on >1B sentence pairs, surprisingly good at paraphrase matching.
- Easily swapped via `SUBCONSCIOUS_EMBEDDING_MODEL` if you want `all-mpnet-base-v2` (higher quality, ~3x slower).

### Cosine similarity
- For sentence embeddings, vector magnitude is mostly an artifact of token count.
- Direction (cosine) captures meaning; magnitude noise is removed.
- ChromaDB exposes cosine via the `hnsw:space` collection metadata.

### TTL as filter, not delete
- We **store** `expires_at` on every entry but never delete on access.
- Recall ignores expired entries; they still count toward `total_entries`.
- Trade-off: storage grows monotonically until a future `purge_expired()` is added.
- Upside: writes stay atomic, no read-path latency from sweeps.

### Lazy model loading
- Importing `sentence-transformers` and loading the model takes ~3-5s.
- We defer until the first `embed()` call so `--help`, `--print-config`, and tests that don't embed all stay fast.

### Ring buffer for `hit_rate_last_100`
- A `collections.deque(maxlen=100)` of booleans is O(1) append and O(n) sum.
- Lives in memory only. Restart resets the window. For a persistent metric, log each outcome and aggregate offline.

## Tag filtering (v0.3)

`recall` and `echo` accept an optional `tags` list; a candidate must share at
least one tag to qualify. The implementation is a **post-filter**: the query
fetches `top_k * 3` nearest neighbours, then drops any whose tags miss. So a
true tag match can fall outside the fetched window when many closer
non-matching entries crowd it out, in which case the result is a miss (and a
miss `similarity` can read `0.0` even though a tagged entry exists). The
remedy is a larger `top_k`, which widens the over-fetch window. A server-side
metadata `where` clause would be exact but ChromaDB's filter semantics over
JSON-encoded tag lists are awkward; the over-fetch keeps the read path simple
and is sufficient at this scale.

## What's deliberately out of scope

- **Background expiry sweep**: relies on filter-at-read.
- **Hot-reload of config**: config is read once at startup.
- **Streaming results**: every tool returns a single dict.
- **Automatic drift remediation**: `drift_report` flags candidates; acting
  on them (forget / split / re-answer) stays a deliberate caller decision.

Each of these is a natural extension if usage demands it.

Namespaces shipped in v0.3: a config-level `namespace` gives each project its
own collection and echo log (the default namespace keeps the legacy names).
