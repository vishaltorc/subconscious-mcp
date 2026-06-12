"""tests/test_redact.py"""
from subconscious_mcp.redact import redact


def test_redacts_known_key_shapes():
    s = (
        "use sk-abc123DEF456ghi789jkl012 and pypi-AgEIcHlwaS5vcmc"
        " and ghp_16C7e42F292c6912E7710c838347Ae178B4a"
    )
    out = redact(s)
    assert "sk-abc" not in out and "pypi-AgEI" not in out and "ghp_16C" not in out
    assert out.count("[REDACTED]") == 3


def test_redacts_bearer_and_env_assignments():
    s = (
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload"
        "\nAPI_KEY=supersecretvalue123"
    )
    out = redact(s)
    assert "eyJhbGci" not in out
    assert "supersecretvalue123" not in out


def test_leaves_normal_text_alone():
    s = "fixed the deploy by running vercel --prod after vercel login"
    assert redact(s) == s
