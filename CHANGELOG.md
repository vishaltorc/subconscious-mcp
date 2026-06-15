# Changelog

## 0.3.0 (unreleased)

The ambient release. Memory stops being something you call and becomes
something that accumulates: Claude Code hooks capture each session, and
per-project namespaces keep that capture from leaking across repositories.

### Added

- **Namespaces**: a config-level `namespace` (env `SUBCONSCIOUS_NAMESPACE`)
  gives each project its own ChromaDB collection and echo log, so memory does
  not leak across repositories. The default namespace keeps the legacy v0.2
  collection and `echo_log.jsonl` names, so existing users upgrade without
  losing memory.
- **Tag filtering on `recall` and `echo`**: pass `tags=[...]` and a candidate
  must share at least one tag. Implemented as a post-filter over an
  over-fetched window (`top_k * 3`).
- **Ambient capture**: optional Claude Code hooks capture one redacted
  task to outcome episode per session.
  - `context.db`, a SQLite inbox (`store.py`): hooks write episodes here; the
    server is the only ChromaDB writer and ingests pending episodes at
    startup.
  - `subconscious-mcp hook --event {session-start,stop,log-only}` CLI for the
    hook handlers (model-free, <100ms, never breaks a session).
  - `subconscious-mcp install-hooks` registers the `SessionStart` and `Stop`
    hooks in Claude Code `settings.json` (atomic write, timestamped backup,
    idempotent, `--dry-run` and `--settings` flags).
  - `SessionStart` injects this project's recent episodes plus a nudge to
    call `recall` before non-trivial work.
  - `Stop` captures the last user-request to assistant-outcome exchange,
    best-effort redacting secrets first (see the README Privacy section).
  - `capture_enabled` (env `SUBCONSCIOUS_CAPTURE_ENABLED`, default `true`)
    disables capture.
- **Episode segregation**: ingested episodes are tagged `kind=episode` and
  excluded from `recall` answers, so mechanical capture never degrades
  curated recall accuracy. Episodes remain visible to `echo` and the
  `SessionStart` context dump.
- **Near-duplicate warning on `remember`**: probes the nearest curated
  neighbour and, when its similarity falls in the band `[0.75, 0.92]`,
  returns `warning="near_duplicate"` with `nearest_task`,
  `nearest_similarity`, and `nearest_entry_id`. A write-time complement to
  the read-time `drift_report`. `skip_if_duplicate=true` skips the write.
- **`echo` exposes `kind`**: each echo carries `kind` (`"memory"` for curated
  entries, `"episode"` for ingested ambient capture).

### Fixed

- `serverInfo.version` reported over MCP `initialize` now reflects the package
  version (the FastMCP server's version field is wired to `__version__`).

## 0.2.0 (2026-06-10)

The echolocation release. Inspired by the project's founding metaphor (bat
sonar), this release turns memory from a store into a sensor and ships the
first mitigation for the first-fill semantic drift failure mode documented
in `validation/results.md`.

### Added

- **`echo(task, top_k=5)` tool**: sonar ping returning the nearest
  non-expired entries with similarities but **without answers**. Safe to
  call anytime: it can never propagate a stale or wrong cached answer,
  and it does not affect hit-rate stats or the echo log.
- **Echo log**: every `recall` appends one JSONL record (timestamp, query,
  nearest entry id (even on a miss), best similarity, hit/miss,
  threshold) to `<storage_dir>/echo_log.jsonl`. Failure-safe (a logging
  error never breaks recall), corruption-tolerant (unparseable lines are
  skipped), and self-compacting (oldest half dropped past
  `echo_log_max_bytes`, atomically).
- **`drift_report(min_hits=3, min_spread=0.08)` tool**: analyzes the echo
  log for first-fill semantic drift candidates: entries whose hits span a
  wide similarity band across distinct query phrasings, i.e. one cached
  answer absorbing a family of queries that may carry different
  interpretations. Costs zero extra LLM or embedding calls.
- **Config**: `echo_log_enabled` (default `true`,
  env `SUBCONSCIOUS_ECHO_LOG_ENABLED`) and `echo_log_max_bytes`
  (default `5000000`, env `SUBCONSCIOUS_ECHO_LOG_MAX_BYTES`).
- **Tests**: 16 new tests (suite: 14 → 30) covering echo geometry, expiry
  filtering, echo log writing/disabling/compaction/corruption tolerance,
  and drift detection (flagging, thresholds, forgotten entries).

### Fixed

- `__init__.__version__` said `0.1.0` while the package was published as
  `0.1.1`; versions are now in sync (`0.2.0` everywhere, including
  `server.json`).

## 0.1.1 (2026-05)

- README cleanup, Claude Desktop config key fix, canonical tagline across
  PyPI / README / `server.json`, badges.
- Dockerfile for Glama verification; `server.json` for the MCP Registry.

## 0.1.0 (2026-05-19)

- Initial release: `recall` / `remember` / `forget` / `stats` over MCP
  stdio, ChromaDB cosine storage, sentence-transformers embeddings,
  env > json > defaults config, rotating file logging.
- 150-task validation study (`validation/`).
