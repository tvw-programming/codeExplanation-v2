import pytest

from src.security.guardrails import (
    is_blocked_path,
    filter_blocked_paths,
    secret_scan,
    redact_secrets,
    REDACTION_PLACEHOLDER,
    SecretFoundError,
    assert_safe_to_read,
)


def test_blocks_env_files():
    assert is_blocked_path(".env")
    assert is_blocked_path(".env.local")
    assert not is_blocked_path("env.md")


def test_blocks_pem_files():
    assert is_blocked_path("server.pem")
    assert not is_blocked_path("server.pem.bak")


def test_blocks_secrets_named_files():
    assert is_blocked_path("secrets.json")
    assert is_blocked_path("my_secrets_file.yaml")


def test_filter_blocked_paths():
    paths = ["src/app.py", ".env", "config/secrets.yaml", "README.md"]
    filtered = filter_blocked_paths(paths)
    assert filtered == ["src/app.py", "README.md"]


def test_secret_scan_raises_on_api_key():
    with pytest.raises(SecretFoundError):
        secret_scan('api_key = "sk-abcdefghijklmnopqrstuvwxyz123456"')


def test_secret_scan_raises_on_private_key():
    with pytest.raises(SecretFoundError):
        secret_scan("-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJ...")


def test_secret_scan_allows_clean_content():
    secret_scan("function hello() { return 'world'; }")


def test_assert_safe_to_read_blocks():
    with pytest.raises(PermissionError):
        assert_safe_to_read(".env")


def test_assert_safe_to_read_allows():
    assert_safe_to_read("src/app.py") is None


def test_redact_secrets_replaces_match_and_reports_true():
    text, redacted = redact_secrets('const apiKey = "sk-abcdefghijklmnopqrstuvwxyz123456";')
    assert redacted is True
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in text
    assert REDACTION_PLACEHOLDER in text


def test_redact_secrets_leaves_clean_content_untouched_and_reports_false():
    text, redacted = redact_secrets("function hello() { return 'world'; }")
    assert redacted is False
    assert text == "function hello() { return 'world'; }"


def test_redact_secrets_handles_multiple_matches():
    text, redacted = redact_secrets(
        'api_key = "sk-abcdefghijklmnopqrstuvwxyz123456"\n'
        "-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJ..."
    )
    assert redacted is True
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in text
    assert "BEGIN RSA PRIVATE KEY" not in text
