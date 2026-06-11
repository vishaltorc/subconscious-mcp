# Contributing to subconscious-mcp

Thanks for looking. The whole codebase is 612 lines across four files; you can read all of it in under an hour. This doc gets you from clone to green PR.

## Setup

```bash
git clone https://github.com/vishaltorc/subconscious-mcp
cd subconscious-mcp
python3.11 -m venv .venv          # any Python >= 3.11; 3.12 recommended
.venv/bin/pip install -e ".[dev]"
```

The first embedding call downloads the all-MiniLM-L6-v2 model (~80MB) into your Hugging Face cache. One-time cost.

## Tests: two lanes

```bash
# Fast lane: no model needed, runs in under a second. Use while iterating.
.venv/bin/pytest -m "not embedding"

# Full suite: loads the model per fixture, ~5 minutes. Run before pushing
# if you touched src/subconscious_mcp/memory.py or anything embedding-adjacent.
.venv/bin/pytest
```

CI runs the fast lane plus ruff on every PR (Python 3.11 and 3.12) and the full suite on 3.12. A test that needs the model must carry `@pytest.mark.embedding`.

## Code layout

| File | Lines | What it owns |
|---|---|---|
| src/subconscious_mcp/server.py | ~123 | CLI, logging, FastMCP wiring |
| src/subconscious_mcp/tools.py | ~150 | Six thin @mcp.tool() shims |
| src/subconscious_mcp/memory.py | ~382 | Embeddings, ChromaDB, echo log, drift detection |
| src/subconscious_mcp/config.py | ~93 | env > json > defaults resolution |

Design rationale lives in [docs/architecture.md](docs/architecture.md). The validation study that motivated the echolocation features is in [validation/](validation/).

## Style

- `ruff check src/ tests/ examples/` must pass. Config is in pyproject.toml.
- Type hints on public functions.
- **No em dashes anywhere**, including docs and comments. Use periods, commas, or colons. CI enforces this. (House rule; the maintainer is serious about it.)
- Match the existing code's comment density. Comments explain constraints, not what the next line does.

## PR process

1. Pick an issue (the `good first issue` label marks evening-sized ones) or open one describing what you want to change. For anything bigger than a small fix, a 2-line issue first saves everyone time.
2. Branch, build, test (fast lane minimum; full suite if you touched memory.py).
3. Open the PR against `main`. The template has the checklist.
4. One maintainer review. Expect direct feedback; nothing personal.

## What gets merged

- Bug fixes with a regression test: fast path to merge.
- Issues labelled `help wanted` or `good first issue`: pre-approved direction, just execute well.
- New features without a prior issue: maybe, but talk first.
- Anything that breaks local-first (phones home, requires an API key to function): no.

## Releases

Maintainer-only (PyPI + MCP Registry + GitHub releases). You never need to touch versioning in a PR.
