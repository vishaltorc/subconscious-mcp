"""src/subconscious_mcp/redact.py

Best-effort secret redaction for ambient capture. Not a guarantee; the
README privacy section states the limits. Pure stdlib, hook-importable.

Pattern minimum lengths:
  sk- and pypi-: {12,} -- the pypi test sample suffix is 15 chars, so
    {16,} would miss it. 12 is the floor: long enough to avoid false
    positives on ordinary hyphenated words, which rarely exceed 12 alnum
    chars after a prefix like sk-.
  GitHub tokens: {20,} -- gh[pousr]_ tokens are always long; 20 is safe.
"""
from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),                  # OpenAI/Anthropic-style
    re.compile(r"\bpypi-[A-Za-z0-9_-]{12,}\b"),                # PyPI tokens
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),             # GitHub tokens
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),           # Slack
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                        # AWS access key id
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),     # bearer tokens
    re.compile(r"(?im)^([A-Z][A-Z0-9_]{2,}(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD)[A-Z0-9_]*)=\S+$"),
]


def redact(text: str) -> str:
    out = text
    for pat in _PATTERNS[:-1]:
        out = pat.sub("[REDACTED]", out)
    # env-style assignments keep the key name, redact the value
    out = _PATTERNS[-1].sub(lambda m: f"{m.group(1)}=[REDACTED]", out)
    return out
