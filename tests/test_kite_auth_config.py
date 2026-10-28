"""
Kite credentials pasted with stray whitespace/quotes must still produce a valid login URL.

Run: python -m pytest tests/test_kite_auth_config.py -v
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.broker import kite_auth  # noqa: E402


@pytest.mark.parametrize("raw", [
    "abc123xyz",
    "  abc123xyz  ",
    "abc123xyz\n",
    "\tabc123xyz\r\n",
    '"abc123xyz"',
    "'abc123xyz'",
    ' " abc123xyz " ',
])
def test_login_url_uses_cleaned_key(monkeypatch, raw):
    monkeypatch.setenv("KITE_API_KEY", raw)
    monkeypatch.setenv("KITE_API_SECRET", ' "secret123"\n')
    assert kite_auth.get_login_url() == "https://kite.zerodha.com/connect/login?api_key=abc123xyz&v=3"
    assert kite_auth._load_config()["api_secret"] == "secret123"


def test_login_url_encodes_unusual_characters(monkeypatch):
    monkeypatch.setenv("KITE_API_KEY", "ab c&d")
    monkeypatch.setenv("KITE_API_SECRET", "s")
    assert kite_auth.get_login_url() == "https://kite.zerodha.com/connect/login?api_key=ab%20c%26d&v=3"


def test_mismatched_quotes_are_kept(monkeypatch):
    monkeypatch.setenv("KITE_API_KEY", "\"abc'")
    monkeypatch.setenv("KITE_API_SECRET", "s")
    assert kite_auth._load_config()["api_key"] == "\"abc'"


def test_config_file_values_are_cleaned(monkeypatch, tmp_path):
    monkeypatch.delenv("KITE_API_KEY", raising=False)
    monkeypatch.delenv("KITE_API_SECRET", raising=False)
    creds = tmp_path / "kite_creds.json"
    creds.write_text('{"api_key": " abc123xyz\\n", "api_secret": "\\"secret123\\""}')
    monkeypatch.setattr(kite_auth, "CONFIG_PATH", creds)
    assert kite_auth._load_config() == {"api_key": "abc123xyz", "api_secret": "secret123"}


def test_blank_or_placeholder_key_not_configured(monkeypatch):
    monkeypatch.setenv("KITE_API_KEY", '  ""  ')
    monkeypatch.setenv("KITE_API_SECRET", "s")
    monkeypatch.setattr(kite_auth, "CONFIG_PATH", Path("does-not-exist.json"))
    assert kite_auth.get_login_url() == "NOT_CONFIGURED"
