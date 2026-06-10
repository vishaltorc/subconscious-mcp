# Changelog

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
