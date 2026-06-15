"""src/subconscious_mcp/redact.py

Best-effort secret redaction for ambient capture. Not a guarantee; the
README privacy section states the limits. Pure stdlib, hook-importable.

Pattern minimum lengths:
  sk- and pypi-: {12,} -- the pypi test sample suffix is 15 chars, so
    {16,} would miss it. 12 is the floor: long enough to avoid false
    positives on ordinary hyphenated words, which rarely exceed 12 chars
    from the class (including hyphens/underscores; the class is not
    alnum-only) after a prefix like sk-.
  GitHub tokens: {20,} -- gh[pousr]_ and github_pat_ tokens are always
    long; 20 is safe.
"""
from __future__ import annotations

import re

_VALUE_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),       # OpenAI/Anthropic-style (sk-ant-, sk-proj-)
    re.compile(r"\bpypi-[A-Za-z0-9_-]{12,}\b"),     # PyPI tokens
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),  # GitHub classic tokens
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),  # GitHub fine-grained tokens
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),  # Slack
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),            # AWS access key id
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),  # bearer tokens
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),  # PEM headers
]

# Known gaps, documented for the README privacy section (Task 13):
# AWS secret access keys (bare 40-char base64), ASIA* temporary key ids,
# bare JWTs outside bearer context, connection-string passwords
# (postgres://user:pass@host), Stripe sk_live_/sk_test_ (underscore form),
# npm_ tokens, Slack xapp-, and mid-prose assignments (KEY=value not on
# its own line). Redaction is best-effort by design.

# Env-style assignment lines keep the key name (and any export prefix);
# only the value is redacted. Quantifiers are bounded so backtracking
# stays linear on adversarial input (ReDoS).
_ENV_ASSIGNMENT = re.compile(
    r"(?im)^((?:export\s+)?)"
    r"([A-Z][A-Z0-9_]{2,64}(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD)[A-Z0-9_]{0,64})"
    r"=\S+$"
)


def redact(text: str) -> str:
    out = text
    for pat in _VALUE_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return _ENV_ASSIGNMENT.sub(lambda m: f"{m.group(1)}{m.group(2)}=[REDACTED]", out)
