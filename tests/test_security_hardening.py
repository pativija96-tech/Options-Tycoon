"""
Security hardening tests — live-execute kill switch + founder auth.

Run: python -m pytest tests/test_security_hardening.py -v
"""

import os
import sys
import json
from pathlib import Path
from datetime import date
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("TRADING_PHASE", "1")
os.environ.setdefault("TRADING_MODE", "qqq")
os.environ.setdefault("SESSION_SECRET", "test-secret-key")
os.environ.setdefault("FOUNDER_ALLOWED_EMAILS", "test@test.com")


NIFTY_SIGNAL = {
    "action": "trade",
    "strategy_type": "iron_condor_250_100",
    "date": date.today().isoformat(),
    "trade": {
        "type": "iron_condor",
        "legs": [
            {"action": "SELL", "option": "CE", "strike": 24750, "premium_est": 12.5},
            {"action": "BUY", "option": "CE", "strike": 24850, "premium_est": 5.0},
            {"action": "SELL", "option": "PE", "strike": 24250, "premium_est": 11.0},
            {"action": "BUY", "option": "PE", "strike": 24150, "premium_est": 4.5},
        ],
    },
}


class TestLiveExecuteKillSwitch:
    """live-execute must never reach a broker unless LIVE_EXECUTE_ENABLED allows the mode."""

    @pytest.fixture(autouse=True)
    def setup_app(self, tmp_path):
        self.output_dir = tmp_path / "output"
        self.output_dir.mkdir()
        (self.output_dir / "today_signal_nifty.json").write_text(json.dumps(NIFTY_SIGNAL))

    def _client(self):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from engine.session import require_founder
        from routes.live import router

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_founder] = lambda: {"user_id": 1, "email": "test@test.com", "name": "Test"}
        return TestClient(app)

    def _execute(self):
        with patch("routes.live.OUTPUT_DIR", self.output_dir):
            with patch("engine.broker.kite_executor.execute_iron_condor") as mock_exec:
                mock_exec.return_value = {"success": True, "placed": 4}
                with patch("db.database.get_connection", return_value=MagicMock()):
                    resp = self._client().post("/api/live/live-execute?mode=nifty")
        return resp, mock_exec

    def test_blocked_when_unset(self, monkeypatch):
        monkeypatch.delenv("LIVE_EXECUTE_ENABLED", raising=False)
        resp, mock_exec = self._execute()
        assert resp.status_code == 403
        assert "disabled" in resp.json()["error"].lower()
        mock_exec.assert_not_called()

    def test_blocked_when_other_mode_enabled(self, monkeypatch):
        monkeypatch.setenv("LIVE_EXECUTE_ENABLED", "qqq")
        resp, mock_exec = self._execute()
        assert resp.status_code == 403
        mock_exec.assert_not_called()

    @pytest.mark.parametrize("value", ["nifty", "NIFTY", "qqq, nifty", "all"])
    def test_allowed_when_mode_enabled(self, monkeypatch, value):
        monkeypatch.setenv("LIVE_EXECUTE_ENABLED", value)
        resp, mock_exec = self._execute()
        assert resp.status_code == 200
        mock_exec.assert_called_once()


class TestRequireFounder:
    """require_founder must not trust client-controlled headers."""

    def _request(self, headers=None, path="/api/live/live-execute"):
        from starlette.requests import Request
        raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
        return Request({"type": "http", "method": "POST", "path": path, "headers": raw, "query_string": b""})

    def test_spoofed_user_id_and_referer_rejected(self):
        from fastapi import HTTPException
        from engine.session import require_founder

        req = self._request({"X-User-Id": "1", "Referer": "https://options-tycoon.com/static/live-nifty.html",
                             "Origin": "https://options-tycoon.com"})
        # Even if user 1 really is the founder in the DB, headers alone must not authenticate.
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = {"email": "test@test.com"}
        with patch("db.database.get_connection", return_value=conn):
            with pytest.raises(HTTPException) as exc:
                require_founder(req)
        assert exc.value.status_code == 403

    def test_wrong_internal_token_rejected(self):
        from fastapi import HTTPException
        from engine.session import require_founder, INTERNAL_TOKEN_HEADER

        with pytest.raises(HTTPException):
            require_founder(self._request({INTERNAL_TOKEN_HEADER: "not-the-token"}))

    def test_internal_token_accepted(self):
        from engine.session import require_founder, INTERNAL_TOKEN_HEADER, INTERNAL_API_TOKEN

        session = require_founder(self._request({INTERNAL_TOKEN_HEADER: INTERNAL_API_TOKEN}))
        assert session["email"] == "scheduler@internal"

    def test_founder_cookie_accepted(self):
        import time
        from engine.session import require_founder, _sign, SESSION_COOKIE_NAME

        payload = json.dumps({"user_id": 1, "email": "test@test.com", "name": "T", "issued_at": int(time.time())})
        cookie = f"{payload}|{_sign(payload)}"
        session = require_founder(self._request({"Cookie": f'{SESSION_COOKIE_NAME}="{cookie}"'}))
        assert session["email"] == "test@test.com"

    def test_kite_callback_still_exempt(self):
        from engine.session import require_founder

        session = require_founder(self._request(path="/api/live/kite-callback"))
        assert session["email"] == "kite-callback"

    def test_missing_allowlist_fails_closed_in_production(self, monkeypatch):
        from fastapi import HTTPException
        import engine.session as s

        monkeypatch.setattr(s, "FOUNDER_ALLOWED_EMAILS", [])
        monkeypatch.setattr(s, "IS_PRODUCTION", True)
        with pytest.raises(HTTPException):
            s.require_founder(self._request())
