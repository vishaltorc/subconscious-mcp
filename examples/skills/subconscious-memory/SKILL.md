---
name: subconscious-memory
description: Use subconscious-mcp MCP tools (recall, remember, echo, drift_report, forget) for local semantic memory. Trigger when starting non-trivial work, before re-solving a problem, after completing a reusable task, on a near_duplicate warning, or when the user mentions memory, cache, or repeated work across sessions.
---

# Subconscious memory discipline

Local semantic memory over MCP. The borderline cases below are where the value
lives: a careless recall reuses a stale answer; a careless skip re-does work.

## Recall before non-trivial work

Before research, multi-file edits, or repeating a workflow, call `recall` with
a short task description (not the full user message).

```text
recall(task="deploy Next.js to Vercel production", threshold=0.85)
```

Then branch on the outcome:

- **Hit at >= 0.88:** reuse `answer` after a quick sanity check (deps, paths,
  dates still apply).
- **Hit below 0.88:** treat as borderline. Verify the answer actually fits
  this task before acting on it; the phrasing matched but the intent may not.
- **Miss, best similarity > 0.7:** do NOT just lower the threshold. Call
  `echo` with the same task first. If the nearest entry is the same task
  family, recall it explicitly (or lower the threshold deliberately); if it is
  a different family, work fresh.
- **Miss, best similarity <= 0.7:** uncharted; do the work normally.

## Remember after a reusable outcome

After producing something reusable (commands, config location, fix pattern):

```text
remember(task="...", answer="...", tags=["project-name", "topic"])
```

Skip secrets, tokens, personal data, and answers that depend on today's file
state.

### Responding to a near_duplicate warning

If `remember` returns `warning="near_duplicate"`, a close curated entry
already exists (similarity in `[0.75, 0.92]`). Do not blindly add a second
copy. Recall or inspect `nearest_entry_id`, compare it to what you were about
to store, then decide:

- **Merge / update:** if it is the same task, `forget(nearest_entry_id)` and
  re-`remember` the better-phrased combined version.
- **Proceed:** if it is genuinely a distinct task that merely reads similar,
  store yours (the write already happened unless you passed
  `skip_if_duplicate=true`).

## Hygiene

- Run `drift_report()` periodically (e.g. when reviewing cache health). For
  flagged entries, `forget` and re-remember more specific variants, or raise
  the recall threshold for that family.
- `stats()` if the user asks whether memory is helping.
- Never trust a hit above 0.85 on interpretive tasks ("extract X" vs "extract
  Y" read almost identically to the embedder); verify first.

## Namespace

Capture and recall are already per-project (the namespace is derived from the
repo). Still tag entries with the project name, and do not recall across
unrelated projects without the user asking.
