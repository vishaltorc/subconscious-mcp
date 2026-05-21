# Architecture

`subconscious-mcp` is intentionally small: four MCP tools, one embedding model,
one persistent vector collection. This document describes the layers, how
data flows through them, and the design decisions that shaped each one.

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
│  tools.py      4 thin @mcp.tool() shims  │
└──────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────┐
│  memory.py    embed / store / query      │
│   - sentence-transformers (lazy)         │
│   - ChromaDB persistent collection       │
│   - in-memory ring buffer for stats      │
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
8. Result is appended to the recent-calls ring buffer (for `stats`).
9. FastMCP serializes the dict and writes it back on stdout.

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

## What's deliberately out of scope (v0.1)

- **Multi-user / multi-collection**: a single user, single collection.
- **Server-side filtering by tag**: tags are stored but not used in recall.
- **Background expiry sweep**: relies on filter-at-read.
- **Hot-reload of config**: config is read once at startup.
- **Streaming results**: every tool returns a single dict.

Each of these is a natural v0.2 extension if usage demands it.
