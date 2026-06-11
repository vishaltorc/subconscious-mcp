## What

<!-- One paragraph: what changes and why. Link the issue if one exists. -->

## Checklist

- [ ] `pytest -m "not embedding"` passes locally (fast lane, < 1s)
- [ ] `pytest` passes locally if you touched memory/embedding code (full suite, ~5 min)
- [ ] `ruff check src/ tests/ examples/` is clean
- [ ] No em dashes in any .md/.py/.toml/.json file (repo convention; CI greps for it)
- [ ] New behaviour has a test
