# v0.3.0 "ambient" design spec

Date: 2026-06-12. Status: approved by Vishal (merge of Claude design + Grok handoff package, refined through two adversarial review rounds).

## Goal

Memory that grows and helps without the agent volunteering tool calls. Install once; sessions start informed and end remembered. All context lands in a local SQLite database the user can query with plain SQL.

## Scope split (decided in adversarial round 1)

- **v0.3.0 (this spec):** ambient capture + foundation + write-time drift guard
- **v0.3.1 (follow-up spec):** geometric consolidation + strength/recency recall ranking, calibrated on real episode data accumulated by v0.3.0, accuracy re-validated on the public harness before any ranking default changes

## v0.3.0 components

### 1. Foundation stack (adopted from Grok handoff, specs in handoff/specs/)

| Item | Source | Note |
|---|---|---|
| serverInfo.version fix | issue #1, FIX-PLAN Task 1 | pass `__version__` to FastMCP |
| Namespaces | issue #8, handoff/specs/namespaces.md | config-level only; collection `subconscious_{namespace}`; echo log per namespace; sanitized ASCII `[a-z0-9_-]+`, alphanumeric edges, max 64 (chromadb 1.5.9 rejects unicode and non-alphanumeric-ending names, verified empirically) |
| Tag filtering | issue #3, handoff/specs/tag-filtering.md | post-filter after over-fetch (top_k x 3); optional `tags` param on recall and echo |

### 2. SQLite context store (`store.py`, new)

- File: `<storage_dir>/context.db`, WAL mode, stdlib `sqlite3` only
- Table `episodes`: `id INTEGER PK, ts REAL, namespace TEXT, project TEXT, session_id TEXT, content TEXT, source TEXT, status TEXT CHECK(status IN ('pending','ingested','skipped'))`, indexes on (namespace, ts) and (status)
- Concurrency rule: hooks and CLI write ONLY to SQLite; the MCP server process is the ONLY ChromaDB writer. This is the multi-process safety boundary.
- Public API: `add_episode()`, `pending_episodes(limit)`, `mark(status, ids)`, `recent_episodes(namespace, n)`

### 3. Hook capture (`subconscious-mcp hook` CLI subcommand)

- Reads the Claude Code hook event JSON from stdin; never loads the embedding model; target under 100ms
- Stop event: extract the final user/assistant resolution pair from the transcript (bounded tail read), redact secrets, insert one episode row with status pending
- SessionStart event: print a context block to stdout containing the last 3 episodes for the derived namespace (pure SQL read) plus one nudge line: "subconscious-mcp holds N memories for this project; recall before non-trivial work"
- Namespace derivation: git root basename, else cwd basename, sanitized (same helper as namespaces feature; shared function)
- Failure rule: exit 0 unconditionally; log failures to `<storage_dir>/logs/hook.log`; a hook must never break a session
- Redaction at capture time: strip strings matching secret shapes (bearer tokens, `sk-`/`pypi-`/`ghp_` style keys, `KEY=value` lines in .env form) before insert

### 4. Calibration task (adversarial round 1, attack 2)

Before finalizing transcript parsing: a logging-only hook variant runs on Vishal's machine for at least one day writing raw payloads to `<storage_dir>/logs/payload_samples/`. Parse code is written against observed payloads, not assumed schema. This is implementation plan step 1.

### 5. install-hooks (`subconscious-mcp install-hooks`)

- Merges SessionStart + Stop entries into the user's Claude Code settings JSON
- Safety (adversarial round 2, attack 7): timestamped backup before write; idempotent (re-run produces no duplicate entries); `--dry-run` prints the exact diff; never modifies or removes existing hook entries
- Tested against fixture settings files: empty, existing unrelated hooks, already-installed

### 6. Episode segregation (adversarial round 1, attack 1)

- Ingestion: on server startup and lazily on tool calls, `Memory.ingest_pending()` embeds pending episodes into ChromaDB tagged `kind=episode`, marks them ingested. Idempotent via status transitions.
- `recall` NEVER returns `kind=episode` entries as answers. Episodes surface only via: SessionStart injection (recency), `echo` (geometry), and future consolidation (v0.3.1).
- Rationale: ambient capture quality is mechanical, not curated; segregation makes capture noise structurally unable to degrade the validated recall accuracy (95.0% at 0.8 on the 150-task study).

### 7. Near-duplicate warning on remember (adopted from Grok handoff I1, FIX-PLAN Task 11)

- On `remember`, query nearest neighbour first; if similarity in [0.75, 0.92], the entry is stored AND the response includes `warning: "near_duplicate"`, `nearest_task`, `nearest_similarity`. An optional `skip_if_duplicate=true` argument stores nothing and returns the warning only. Base spec: handoff/specs/near-duplicate-warning.md
- This is write-time first-fill drift prevention, complementing read-time detection (drift_report) and future read-time mitigation (v0.3.1 consolidation)

### 8. Privacy surface (adversarial round 2, attack 8)

- `capture_enabled` config key (default true; hooks check it on every fire and no-op when false), env `SUBCONSCIOUS_CAPTURE_ENABLED`
- README privacy section: what is captured, where it lives, redaction limits, and the one-line wipe (`rm -rf ~/.subconscious-mcp`)

### 9. Docs and skill

- `examples/skills/subconscious-memory/SKILL.md` + `examples/CLAUDE.md.snippet` refined (Grok scaffolds), encoding the borderline protocol (miss with similarity > 0.7: echo first; hit below 0.88: verify before acting)
- README: ambient section, config table additions, privacy section
- Stale docs sweep per handoff/STALE_DOCS_CHECKLIST.md

## Config additions

| Key | Default | Env |
|---|---|---|
| namespace | "default" | SUBCONSCIOUS_NAMESPACE |
| capture_enabled | true | SUBCONSCIOUS_CAPTURE_ENABLED |

(v0.3.1 will add consolidation and ranking knobs; deliberately absent here.)

## Explicitly rejected alternatives (with reasons)

| Alternative | Rejected because |
|---|---|
| Hooks import Memory library directly (Grok FIX-PLAN Task 4 mechanics) | loads 400MB model per hook fire (~5s lag); second process writing ChromaDB concurrently risks corruption |
| Similarity recall on UserPromptSubmit hook | forces model load into every prompt; latency kills ambient feel |
| LLM-written episode distillation | no LLM inside the server (local-first); v0.4 direction via agent-in-loop or MCP sampling |
| Single store via sqlite-vec | migration off ChromaDB is v0.5-sized; recorded as future direction |
| Strength/recency ranking ON by default in v0.3.0 | invalidates published validation numbers; ships neutral in v0.3.1 behind re-validation |
| Raw transcript chunk capture | storage bloat; drift breeding ground per validation findings |

## Testing bar

- TDD throughout; all store.py, capture parsing, redaction, install-hooks merging, near-duplicate logic: fast lane (no model, sub-second)
- Ingestion + segregation: embedding-marked tests
- End-to-end: hook fixture payload through capture, ingest, SessionStart injection assertion
- Dogfood gate: runs on Vishal's machine for several days; context.db inspected with plain SQL before release
- Existing 30 tests stay green; ruff clean; zero em dashes (CI enforces)

## Done definition (v0.3.0)

- [ ] Foundation: #1 fixed, namespaces + tag filtering shipped with tests
- [ ] context.db + hook capture + install-hooks + SessionStart injection working end to end on a real machine
- [ ] Near-duplicate warning live
- [ ] Episode segregation enforced and tested
- [ ] Redaction + privacy docs
- [ ] Payload calibration evidence in repo (sanitized samples or schema notes)
- [ ] Public harness still green; docs refreshed; skill + snippet shipped
