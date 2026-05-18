import json

from gsa.security.redaction import REDACTED, redact_secrets, register_secret


def test_redact_secrets_handles_nested_payloads_and_exceptions(monkeypatch):
    key = "sk-" + "testsecret1234567890abcdef"
    monkeypatch.setenv("BIGMODEL_API_KEY", key)
    register_secret(key)

    payload = {
        "api_key": key,
        "nested": ["Bearer " + key, RuntimeError("token=" + key)],
        "safe": "hello",
    }

    redacted = redact_secrets(payload)
    encoded = json.dumps(redacted, ensure_ascii=False)

    assert key not in encoded
    assert REDACTED in encoded
    assert redacted["api_key"] == REDACTED
    assert redacted["safe"] == "hello"


def test_redact_common_github_and_long_token_shapes():
    token = "github_pat_" + "1234567890abcdefghijklmnopqrstuvwxyz"
    long_value = "abc1234567890" + "abcdefghijklmnopqrstuvwxyzABCDEF"
    text = f"authorization: Bearer {token}\nraw={long_value}"

    redacted = redact_secrets(text)

    assert token not in redacted
    assert long_value not in redacted
    assert REDACTED in redacted
