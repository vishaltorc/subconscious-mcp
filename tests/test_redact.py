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


def test_redacts_aws_slack_and_pem():
    s = ("aws AKIA0123456789ABCDEF and slack xoxb-1234567890-abcdefghij\n"
         "-----BEGIN RSA PRIVATE KEY-----")
    out = redact(s)
    assert "AKIA0123456789ABCDEF" not in out
    assert "xoxb-1234567890" not in out
    assert "BEGIN RSA PRIVATE KEY" not in out


def test_env_assignment_preserves_key_name():
    assert redact("OPENAI_API_KEY=sk_value_here123") == "OPENAI_API_KEY=[REDACTED]"
    assert redact("export DB_PASSWORD=hunter2") == "export DB_PASSWORD=[REDACTED]"


def test_github_fine_grained_token():
    out = redact("github_pat_11ABCDEFG0123456789_abcdefghijklmnop")
    assert "github_pat_11ABC" not in out


def test_redact_is_fast_on_adversarial_input():
    import time
    start = time.perf_counter()
    redact("KEY" * 30_000)
    assert time.perf_counter() - start < 0.5
