"""
Options Tycoon — End-to-End API Test Suite

Tests all major features via HTTP API calls to a live server at localhost:8000.
Uses httpx synchronous client.

Usage: python e2e_test.py
"""

import httpx
import sys
from datetime import datetime, timezone

BASE_URL = "http://127.0.0.1:8000"  # Use 127.0.0.1 (uvicorn binds here; "localhost" may resolve to IPv6)

results: list[tuple[str, bool, str]] = []  # (test_name, passed, detail)


def record(name: str, passed: bool, detail: str = ""):
    results.append((name, passed, detail))
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def main():
    print("=" * 60)
    print("OPTIONS TYCOON — End-to-End API Tests")
    print("=" * 60)
    print(f"Target: {BASE_URL}")
    print()

    client = httpx.Client(base_url=BASE_URL, timeout=15.0)

    profile_id = None
    trade_id = None
    session_id = None

    # -----------------------------------------------------------------------
    # 1. Health Check
    # -----------------------------------------------------------------------
    print("[1] Health Check")
    try:
        r = client.get("/health")
        ok = r.status_code == 200 and r.json().get("status") == "ok"
        record("GET /health", ok, f"status={r.status_code}")
    except Exception as e:
        record("GET /health", False, str(e))

    # -----------------------------------------------------------------------
    # 2. Profile Creation
    # -----------------------------------------------------------------------
    print("\n[2] Profile Creation")
    try:
        r = client.post("/api/profiles", json={"name": "E2E_Test"})
        ok = r.status_code == 201
        if ok:
            profile_id = r.json()["id"]
        record("POST /api/profiles", ok, f"profile_id={profile_id}")
    except Exception as e:
        record("POST /api/profiles", False, str(e))

    # -----------------------------------------------------------------------
    # 3. List Tickers
    # -----------------------------------------------------------------------
    print("\n[3] List Tickers")
    try:
        r = client.get("/api/tickers")
        data = r.json()
        ok = r.status_code == 200 and "tickers" in data and len(data["tickers"]) > 0
        record("GET /api/tickers", ok, f"count={len(data.get('tickers', []))}")
    except Exception as e:
        record("GET /api/tickers", False, str(e))

    # -----------------------------------------------------------------------
    # 4. Load Chain
    # -----------------------------------------------------------------------
    print("\n[4] Load Chain")
    try:
        r = client.get("/api/chain/NIFTY")
        data = r.json()
        ok = r.status_code == 200 and "chain" in data and len(data["chain"]) > 0
        record("GET /api/chain/NIFTY", ok, f"rows={len(data.get('chain', []))}")
    except Exception as e:
        record("GET /api/chain/NIFTY", False, str(e))

    # -----------------------------------------------------------------------
    # 5. IV Rank
    # -----------------------------------------------------------------------
    print("\n[5] IV Rank")
    try:
        r = client.get("/api/iv-rank/NIFTY")
        data = r.json()
        ok = r.status_code == 200 and "iv_rank" in data
        record("GET /api/iv-rank/NIFTY", ok, f"iv_rank={data.get('iv_rank')}")
    except Exception as e:
        record("GET /api/iv-rank/NIFTY", False, str(e))

    # -----------------------------------------------------------------------
    # 6. Execute Trade
    # -----------------------------------------------------------------------
    print("\n[6] Execute Trade")
    try:
        trade_payload = {
            "profile_id": profile_id,
            "ticker": "NIFTY",
            "strategy_type": "long_call",
            "legs": [
                {
                    "contract_type": "call",
                    "strike": 22500,
                    "expiration": "2025-02-27",
                    "quantity": 1,
                    "action": "buy",
                }
            ],
            "chain_opened_at": datetime.now(timezone.utc).isoformat(),
            "confirmation_proceeded": True,
        }
        r = client.post("/api/trades", json=trade_payload)
        data = r.json()
        ok = r.status_code == 200 and "id" in data
        if ok:
            trade_id = data["id"]
        record("POST /api/trades", ok, f"trade_id={trade_id}, cost={data.get('entry_price')}")
    except Exception as e:
        record("POST /api/trades", False, str(e))

    # -----------------------------------------------------------------------
    # 7. Get Positions
    # -----------------------------------------------------------------------
    print("\n[7] Get Positions")
    try:
        r = client.get(f"/api/positions/{profile_id}")
        data = r.json()
        ok = r.status_code == 200 and "positions" in data
        record("GET /api/positions/{id}", ok, f"count={len(data.get('positions', []))}")
    except Exception as e:
        record("GET /api/positions/{id}", False, str(e))

    # -----------------------------------------------------------------------
    # 8. Get Behavioral Metrics
    # -----------------------------------------------------------------------
    print("\n[8] Behavioral Metrics")
    try:
        r = client.get(f"/api/behavioral/{profile_id}")
        data = r.json()
        ok = r.status_code == 200 and "phase" in data
        record("GET /api/behavioral/{id}", ok, f"phase={data.get('phase')}")
    except Exception as e:
        record("GET /api/behavioral/{id}", False, str(e))

    # -----------------------------------------------------------------------
    # 9. Get Achievements
    # -----------------------------------------------------------------------
    print("\n[9] Achievements")
    try:
        r = client.get(f"/api/behavioral/{profile_id}/achievements")
        data = r.json()
        ok = r.status_code == 200 and "xp" in data and "level" in data
        record("GET /api/behavioral/{id}/achievements", ok, f"xp={data.get('xp')}, level={data.get('level')}")
    except Exception as e:
        record("GET /api/behavioral/{id}/achievements", False, str(e))

    # -----------------------------------------------------------------------
    # 10. Start Simulation
    # -----------------------------------------------------------------------
    print("\n[10] Start Simulation")
    try:
        r = client.post("/api/simulation/start", json={"profile_id": profile_id, "ticker": "NIFTY"})
        data = r.json()
        ok = r.status_code == 200 and "session_id" in data
        if ok:
            session_id = data["session_id"]
        record("POST /api/simulation/start", ok, f"session_id={session_id}")
    except Exception as e:
        record("POST /api/simulation/start", False, str(e))

    # -----------------------------------------------------------------------
    # 11. Get Tick
    # -----------------------------------------------------------------------
    print("\n[11] Get Tick")
    try:
        r = client.get("/api/simulation/tick", params={"session_id": session_id})
        data = r.json()
        ok = r.status_code == 200 and "current_price" in data
        record("GET /api/simulation/tick", ok, f"price={data.get('current_price')}")
    except Exception as e:
        record("GET /api/simulation/tick", False, str(e))

    # -----------------------------------------------------------------------
    # 12. Get Simulation State
    # -----------------------------------------------------------------------
    print("\n[12] Simulation State")
    try:
        r = client.get("/api/simulation/state", params={"session_id": session_id})
        data = r.json()
        ok = r.status_code == 200 and "session_active" in data
        record("GET /api/simulation/state", ok, f"active={data.get('session_active')}")
    except Exception as e:
        record("GET /api/simulation/state", False, str(e))

    # -----------------------------------------------------------------------
    # 13. Risk Check
    # -----------------------------------------------------------------------
    print("\n[13] Risk Check")
    try:
        r = client.get(
            f"/api/risk-check/{profile_id}",
            params={"position_pct": 8, "ticker": "NIFTY", "expiry": "2025-02-26"},
        )
        data = r.json()
        ok = r.status_code == 200 and "warnings" in data
        record("GET /api/risk-check/{id}", ok, f"warnings={len(data.get('warnings', []))}")
    except Exception as e:
        record("GET /api/risk-check/{id}", False, str(e))

    # -----------------------------------------------------------------------
    # 14. Close Position
    # -----------------------------------------------------------------------
    print("\n[14] Close Position")
    try:
        r = client.post(f"/api/positions/{trade_id}/close", json={"outcome_tag": "success"})
        data = r.json()
        ok = r.status_code == 200 and data.get("status") == "closed"
        record("POST /api/positions/{trade_id}/close", ok, f"pnl={data.get('realized_pnl')}")
    except Exception as e:
        record("POST /api/positions/{trade_id}/close", False, str(e))

    # -----------------------------------------------------------------------
    # 15. Get Trade History
    # -----------------------------------------------------------------------
    print("\n[15] Trade History")
    try:
        r = client.get(f"/api/trades/{profile_id}")
        data = r.json()
        ok = r.status_code == 200 and isinstance(data, list)
        record("GET /api/trades/{id}", ok, f"count={len(data)}")
    except Exception as e:
        record("GET /api/trades/{id}", False, str(e))

    # -----------------------------------------------------------------------
    # 16. Log Telemetry
    # -----------------------------------------------------------------------
    print("\n[16] Log Telemetry")
    try:
        telemetry_payload = {
            "trade_id": trade_id,
            "risk_gate_warnings": ["risk_gate"],
            "trader_decision": "proceeded",
        }
        r = client.post(f"/api/telemetry/{profile_id}", json=telemetry_payload)
        data = r.json()
        ok = r.status_code == 200 and "id" in data
        record("POST /api/telemetry/{id}", ok, f"telemetry_id={data.get('id')}")
    except Exception as e:
        record("POST /api/telemetry/{id}", False, str(e))

    # -----------------------------------------------------------------------
    # 17. Get Monthly P&L
    # -----------------------------------------------------------------------
    print("\n[17] Monthly P&L")
    try:
        r = client.get(f"/api/behavioral/{profile_id}/monthly")
        data = r.json()
        ok = r.status_code == 200 and "months" in data
        record("GET /api/behavioral/{id}/monthly", ok, f"months={len(data.get('months', []))}")
    except Exception as e:
        record("GET /api/behavioral/{id}/monthly", False, str(e))

    # -----------------------------------------------------------------------
    # 18. EOD Data
    # -----------------------------------------------------------------------
    print("\n[18] EOD Data")
    try:
        r = client.get("/api/eod/NIFTY")
        data = r.json()
        ok = r.status_code == 200 and "data" in data
        record("GET /api/eod/NIFTY", ok, f"source={data.get('source')}")
    except Exception as e:
        record("GET /api/eod/NIFTY", False, str(e))

    # -----------------------------------------------------------------------
    # 19. Compare Mode
    # -----------------------------------------------------------------------
    print("\n[19] Compare Mode")
    try:
        r = client.get(f"/api/compare/{profile_id}")
        data = r.json()
        ok = r.status_code == 200 and ("sim" in data or "sim_metrics" in data)
        record("GET /api/compare/{id}", ok, f"keys={list(data.keys())[:4]}")
    except Exception as e:
        record("GET /api/compare/{id}", False, str(e))

    # -----------------------------------------------------------------------
    # 20. Delete Profile
    # -----------------------------------------------------------------------
    print("\n[20] Delete Profile")
    try:
        r = client.delete(f"/api/profiles/{profile_id}")
        ok = r.status_code == 204
        record("DELETE /api/profiles/{id}", ok, f"status={r.status_code}")
    except Exception as e:
        record("DELETE /api/profiles/{id}", False, str(e))

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    client.close()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, p, _ in results if p)
    failed = sum(1 for _, p, _ in results if not p)
    total = len(results)

    print(f"  Total:  {total}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print()

    if failed > 0:
        print("  FAILED TESTS:")
        for name, p, detail in results:
            if not p:
                print(f"    ✗ {name} — {detail}")
        print()

    if failed == 0:
        print("  ✓ ALL TESTS PASSED")
    else:
        print(f"  ✗ {failed}/{total} TESTS FAILED")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
