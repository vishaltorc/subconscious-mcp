# task.md — finish and ship subconscious-mcp v0.2.0 ("echolocation")

Handoff file. Written to be executed top-to-bottom by a human or an agent
session running on a machine with this repo cloned and full network access
(PyPI + huggingface.co). Each task has explicit commands and an acceptance
check. Do the tasks in order; if an acceptance check fails, stop and report
the failure instead of continuing.

## Context (read first)

- Branch `claude/admiring-albattani-d5783r` (commit `c44412c`) contains the
  complete v0.2.0 implementation:
  - `echo(task, top_k)` tool — nearest entries with similarities, no answers
  - echo log — JSONL record of every recall at `<storage_dir>/echo_log.jsonl`
  - `drift_report(min_hits, min_spread)` tool — first-fill semantic drift
    detection from the echo log (the mitigation deferred in
    `validation/results.md`)
  - config knobs `echo_log_enabled` / `echo_log_max_bytes`, docs, examples,
    CHANGELOG, version 0.2.0 everywhere
- The branch was developed in a sandbox that blocks huggingface.co. The
  10 embedding-free tests passed there, plus CLI checks; the 20
  embedding-dependent tests have **not been executed yet**. Task 1 closes
  that gap.
- `examples/transcript_output.txt` is still the v0.1 four-tool capture.
  Task 3 regenerates it.

## Credentials policy

This file intentionally contains **no credentials**. Supply them at run
time via environment or OS keychain, never in files that get committed:

- PyPI: `TWINE_USERNAME=__token__` + `TWINE_PASSWORD=<pypi-token>`
  (or `~/.pypirc`, or keyring)
- MCP Registry: `mcp-publisher login github` (interactive)

Do not paste tokens into MCP client configs, chat sessions, or this file.

---

## Task 1 — Run the full test suite (closes the verification gap)

```bash
cd <repo-root>
git checkout claude/admiring-albattani-d5783r
python3.12 -m venv .venv          # any Python >= 3.11
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -v
```

Notes:
- First run downloads the ~80MB sentence-transformer model into the HF cache
  and is slow (~5s model load per test fixture; expect a few minutes total).

**Acceptance: `30 passed`.** If any embedding-dependent test fails, fix it
on this branch before proceeding (the embedding-free 10 are already known
green; a failure is most likely a similarity-threshold assumption in a new
test, e.g. `test_recall_writes_echo_log` assumes unrelated sentences have
cosine similarity > 0).

## Task 2 — Verify the MCP surface end to end

```bash
# Make sure the venv's bin is on PATH so the client can spawn the server:
export PATH="$PWD/.venv/bin:$PATH"
subconscious-mcp --version        # expect: subconscious-mcp 0.2.0
subconscious-mcp --print-config   # expect echo_log_enabled / echo_log_max_bytes fields
```

Optionally register with a local MCP client and confirm **six** tools appear
(recall, remember, echo, drift_report, forget, stats):

```bash
claude mcp add subconscious-mcp -- subconscious-mcp
```

**Acceptance:** version is 0.2.0, config shows the two new keys, client
lists six tools.

## Task 3 — Regenerate the example transcript

```bash
.venv/bin/python examples/transcript_client.py | tee examples/transcript_output.txt
```

Notes:
- To avoid polluting real memory, point storage elsewhere first. The MCP
  SDK spawns the server with a minimal environment, so an exported env var
  may not propagate; the reliable way is a temporary
  `~/.subconscious-mcp/config.json` containing
  `{"storage_dir": "/tmp/subconscious-mcp-demo"}` — remove it (and
  `/tmp/subconscious-mcp-demo`) afterwards.

**Acceptance:** the new transcript shows `list_tools` with six tools, an
`echo (sonar ping)` result with similarities but **no `answer` field**, and
a `drift_report` result. Commit the regenerated file to the branch.

## Task 4 — Merge and tag

1. Merge `claude/admiring-albattani-d5783r` into `main` (PR or merge —
   owner's choice).
2. Tag the release on main:

```bash
git tag v0.2.0
git push origin v0.2.0
```

**Acceptance:** `main` contains the v0.2.0 changes; tag `v0.2.0` exists on
the remote.

## Task 5 — Publish to PyPI

From the merged `main`:

```bash
.venv/bin/pip install build twine
rm -rf dist/
.venv/bin/python -m build
.venv/bin/twine check dist/*
.venv/bin/twine upload dist/*
```

**Acceptance:** in a fresh venv, `pip install subconscious-mcp==0.2.0`
succeeds and `subconscious-mcp --version` prints 0.2.0.

## Task 6 — Refresh the MCP Registry entry

`server.json` is already bumped to 0.2.0 with the new tagline. After the
PyPI release is live:

```bash
mcp-publisher login github
mcp-publisher publish
```

**Acceptance:**
`https://registry.modelcontextprotocol.io/v0/servers?search=subconscious`
shows version 0.2.0.

## Task 7 — Drift-replay demo (the differentiated deliverable)

Goal: show that `drift_report` catches the "numbers vs digits" first-fill
drift family from the threshold-0.8 validation run **before** any judge
flags a wrong answer — using only echo-log data.

1. Inspect `validation/results_threshold_0.8.csv` to learn its schema
   (per-task rows; identify the cache-hit rows, the matched/stored task,
   and the similarity column).
2. Write `validation/replay_drift.py` that:
   - creates a `Memory` with a temp `storage_dir`,
   - `remember()`s each seed task that received cache hits (so entry ids
     exist), keeping a map seed-task → entry_id,
   - appends one echo-log line per cache-hit row (query = the paraphrase,
     entry_id = the matched seed's id, similarity from the CSV, hit = true),
   - calls `memory.drift_report(min_hits=3, min_spread=0.08)` and prints
     the candidates.
3. Record findings in `validation/drift_replay.md`: the flagged candidates,
   whether the digits/numbers entry is among them (expected: yes, with
   spread ≈ 0.12 given hits at 0.82–0.94), how many *clean* entries were
   false-flagged, and how results shift at `min_spread` 0.05 / 0.08 / 0.12.

**Acceptance:** the digits/numbers entry is flagged; `drift_replay.md` is
committed with the precision/recall observations of the detector on this
run.

## Task 8 (optional) — The writeup

Draft a blog post / short paper: "First-fill semantic drift, and detecting
it by echolocation." Structure: the failure mode (from
`validation/results.md`) → why identical-input cache research misses it →
echo-log detection (Task 7 numbers as evidence) → relation to known
GPTCache false-hit literature (cite honestly: the *propagation framing* and
the zero-cost detector are the new parts, not the existence of false hits).

---

## Done definition

- [ ] 30/30 tests pass locally
- [ ] Six tools verified over real MCP stdio; transcript regenerated
- [ ] Merged to main, tagged v0.2.0
- [ ] PyPI 0.2.0 live and installable
- [ ] MCP Registry shows 0.2.0
- [ ] `validation/drift_replay.md` committed with detector results
- [ ] (optional) writeup drafted
