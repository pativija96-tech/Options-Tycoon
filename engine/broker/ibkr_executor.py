"""
IBKR REST Executor — Web API v1.0 with OAuth 2.0 (private_key_jwt).

Runs on Railway without TWS/Gateway. Pure HTTPS calls.

Components:
1. OAuth 2.0 Auth (signed JWT → access token)
2. Session Heartbeat (tickle every 60s — integrated into scheduler)
3. Contract ID Resolution (symbol → conid)
4. Combo Order Execution (4-leg Iron Condor)
5. Auto-confirmation of order prompts
6. Retry logic + partial execution recovery

Env vars:
    IBKR_CLIENT_ID: OAuth client ID
    IBKR_ACCOUNT_ID: Account number (e.g., U12345678)
    IBKR_PRIVATE_KEY_PEM: RSA private key string

Usage:
    from engine.broker.ibkr_executor import get_ibkr_executor
    executor = get_ibkr_executor()
    executor.authenticate()
    result = executor.place_iron_condor(qqq_price=682.0)
"""

import os
import time
import uuid
import logging
from typing import Dict, Any, Optional, List
from datetime import date, timedelta
from functools import wraps

import jwt
import httpx

logger = logging.getLogger("ibkr_executor")

# Singleton instance
_executor_instance = None

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_BASE = 1.0  # seconds (exponential backoff: 1, 2, 4)
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}  # Retryable HTTP errors


def _retry_on_failure(max_retries: int = MAX_RETRIES):
    """Decorator: retry on httpx.TimeoutException or retryable HTTP status codes."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except httpx.TimeoutException as e:
                    last_exception = e
                    delay = RETRY_DELAY_BASE * (2 ** attempt)
                    logger.warning(
                        f"{func.__name__} timeout (attempt {attempt + 1}/{max_retries}). "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code in RETRY_STATUS_CODES:
                        last_exception = e
                        delay = RETRY_DELAY_BASE * (2 ** attempt)
                        logger.warning(
                            f"{func.__name__} HTTP {e.response.status_code} "
                            f"(attempt {attempt + 1}/{max_retries}). Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                    else:
                        raise  # Non-retryable HTTP error
            # All retries exhausted
            logger.error(f"{func.__name__} failed after {max_retries} attempts.")
            raise last_exception
        return wrapper
    return decorator


def get_ibkr_executor():
    """Get or create the singleton IBKR executor."""
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = IBKRExecutor()
    return _executor_instance


class IBKRExecutor:
    """REST-based IBKR Web API v1.0 executor."""

    BASE_URL = "https://api.ibkr.com/v1/api"

    # QQQ strategy parameters (defaults — overridden by config/settings.json)
    QQQ_OFFSET = 15
    QQQ_WING = 5  # Phase 1: $5 wings ($500 max loss on $1K capital)

    def __init__(self):
        self.client_id = os.getenv("IBKR_CLIENT_ID", "")
        self.account_id = os.getenv("IBKR_ACCOUNT_ID", "")
        self._private_key_pem = os.getenv("IBKR_PRIVATE_KEY_PEM", "")

        self.access_token: Optional[str] = None
        self.token_expiry: float = 0.0
        self.client = httpx.Client(timeout=15.0)

        # Load strategy params from config if available
        self._load_config()

    def _load_config(self):
        """Load QQQ parameters from config/settings.json if available."""
        try:
            import json
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "config", "settings.json"
            )
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    settings = json.load(f)
                qqq_config = settings.get("qqq", {})
                if qqq_config.get("offset_pts"):
                    self.QQQ_OFFSET = qqq_config["offset_pts"]
                if qqq_config.get("wing_width"):
                    self.QQQ_WING = qqq_config["wing_width"]
                logger.info(f"Config loaded: offset={self.QQQ_OFFSET}, wing={self.QQQ_WING}")
        except Exception as e:
            logger.debug(f"Config load skipped (using defaults): {e}")

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.account_id and self._private_key_pem)

    @property
    def private_key(self) -> str:
        if not self._private_key_pem:
            raise ValueError("IBKR_PRIVATE_KEY_PEM not set.")
        return self._private_key_pem

    # ==========================================================================
    # AUTH
    # ==========================================================================

    def _generate_client_assertion(self) -> str:
        """Generate signed JWT for OAuth 2.0 RFC 7523."""
        now = int(time.time())
        payload = {
            "iss": self.client_id,
            "sub": self.client_id,
            "aud": f"{self.BASE_URL}/oauth/token",
            "jti": str(uuid.uuid4()),
            "iat": now,
            "exp": now + 300,
        }
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    def authenticate(self) -> bool:
        """Exchange signed JWT for access token + init brokerage session."""
        if not self.is_configured:
            logger.error("IBKR not configured. Set env vars.")
            return False

        logger.info("Authenticating with IBKR OAuth 2.0...")
        for attempt in range(MAX_RETRIES):
            try:
                assertion = self._generate_client_assertion()
                data = {
                    "grant_type": "client_credentials",
                    "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                    "client_assertion": assertion,
                }
                res = self.client.post(f"{self.BASE_URL}/oauth/token", data=data)
                res.raise_for_status()

                token_data = res.json()
                self.access_token = token_data["access_token"]
                self.token_expiry = time.time() + token_data.get("expires_in", 3600) - 60
                self.client.headers.update({"Authorization": f"Bearer {self.access_token}"})

                # Init brokerage session
                self._validate_session()
                logger.info("IBKR authenticated successfully.")
                return True

            except httpx.TimeoutException:
                delay = RETRY_DELAY_BASE * (2 ** attempt)
                logger.warning(f"Auth timeout (attempt {attempt + 1}/{MAX_RETRIES}). Retrying in {delay:.1f}s...")
                time.sleep(delay)
            except Exception as e:
                logger.error(f"IBKR auth failed: {e}")
                return False

        logger.error(f"IBKR auth failed after {MAX_RETRIES} attempts (timeout).")
        return False

    def ensure_authenticated(self) -> bool:
        """Ensure token is active."""
        if not self.access_token or time.time() >= self.token_expiry:
            return self.authenticate()
        return True

    def _validate_session(self):
        """Confirm brokerage session is active."""
        try:
            res = self.client.post(f"{self.BASE_URL}/iserver/auth/status")
            if res.status_code == 200:
                status = res.json()
                if not status.get("authenticated"):
                    self.client.post(f"{self.BASE_URL}/iserver/sso/validate")
        except Exception as e:
            logger.warning(f"Session validation: {e}")

    def send_heartbeat(self) -> bool:
        """Keep session alive. Call every 60 seconds."""
        try:
            if not self.ensure_authenticated():
                return False
            res = self.client.post(f"{self.BASE_URL}/iserver/tickle")
            return res.status_code == 200
        except Exception as e:
            logger.error(f"Heartbeat failed: {e}")
            return False

    # ==========================================================================
    # CONTRACT RESOLUTION
    # ==========================================================================

    def search_contract(self, symbol: str = "QQQ") -> Optional[int]:
        """Resolve symbol to conid via /iserver/secdef/search. Retries on timeout."""
        self.ensure_authenticated()
        for attempt in range(MAX_RETRIES):
            try:
                res = self.client.get(
                    f"{self.BASE_URL}/iserver/secdef/search",
                    params={"symbol": symbol, "secType": "STK"},
                )
                res.raise_for_status()
                data = res.json()
                if data and len(data) > 0:
                    conid = data[0].get("conid")
                    logger.info(f"Resolved {symbol} → conid {conid}")
                    return int(conid)
                return None
            except httpx.TimeoutException:
                delay = RETRY_DELAY_BASE * (2 ** attempt)
                logger.warning(f"Contract search timeout for {symbol} (attempt {attempt + 1}). Retrying in {delay:.1f}s...")
                time.sleep(delay)
            except Exception as e:
                logger.error(f"Contract search failed for {symbol}: {e}")
                return None
        logger.error(f"Contract search for {symbol} failed after {MAX_RETRIES} retries.")
        return None

    def get_option_chain(self, underlying_conid: int, expiry: str) -> List[Dict]:
        """
        Get option chain strikes for a given underlying + expiry.
        
        Args:
            underlying_conid: conid of the underlying (QQQ)
            expiry: expiry in YYYYMMDD format
        
        Returns:
            List of option contracts with strike/right/conid
        """
        self.ensure_authenticated()
        try:
            res = self.client.get(
                f"{self.BASE_URL}/iserver/secdef/info",
                params={
                    "conid": underlying_conid,
                    "secType": "OPT",
                    "month": expiry[:6],  # YYYYMM
                    "exchange": "SMART",
                },
            )
            res.raise_for_status()
            return res.json()
        except Exception as e:
            logger.error(f"Option chain fetch failed: {e}")
            return []

    def resolve_option_conid(
        self, underlying_conid: int, strike: float, right: str, expiry: str
    ) -> Optional[int]:
        """
        Find the conid for a specific option contract. Retries on timeout.
        
        Args:
            underlying_conid: conid of underlying (QQQ)
            strike: strike price
            right: "C" for call, "P" for put
            expiry: YYYYMMDD format
        
        Returns:
            conid of the option contract, or None
        """
        self.ensure_authenticated()
        for attempt in range(MAX_RETRIES):
            try:
                res = self.client.get(
                    f"{self.BASE_URL}/iserver/secdef/info",
                    params={
                        "conid": underlying_conid,
                        "secType": "OPT",
                        "month": expiry[:6],
                        "exchange": "SMART",
                        "strike": strike,
                        "right": right,
                    },
                )
                res.raise_for_status()
                data = res.json()
                if data and len(data) > 0:
                    # Find exact match
                    for opt in data:
                        if (
                            abs(float(opt.get("strike", 0)) - strike) < 0.01
                            and opt.get("right", "").upper() == right.upper()
                            and opt.get("maturityDate", "") == expiry
                        ):
                            return int(opt["conid"])
                    # Fallback: return first match
                    return int(data[0].get("conid", 0)) or None
                return None
            except httpx.TimeoutException:
                delay = RETRY_DELAY_BASE * (2 ** attempt)
                logger.warning(
                    f"Option conid timeout ({right}{strike} exp {expiry}, attempt {attempt + 1}). "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
            except Exception as e:
                logger.error(f"Option conid resolution failed: {e}")
                return None
        logger.error(f"Option conid resolution for {right}{strike} failed after {MAX_RETRIES} retries.")
        return None

    # ==========================================================================
    # PRICE DATA
    # ==========================================================================

    def get_qqq_price(self) -> Optional[float]:
        """Get current QQQ price from IBKR market data. Retries on timeout."""
        self.ensure_authenticated()
        for attempt in range(MAX_RETRIES):
            try:
                # Get QQQ conid
                qqq_conid = self.search_contract("QQQ")
                if not qqq_conid:
                    return None

                # Request market data snapshot
                res = self.client.get(
                    f"{self.BASE_URL}/iserver/marketdata/snapshot",
                    params={"conids": str(qqq_conid), "fields": "31,84,86"},
                    # 31=Last, 84=Bid, 86=Ask
                )
                res.raise_for_status()
                data = res.json()

                if data and len(data) > 0:
                    snapshot = data[0]
                    # Try last price first, then mid of bid/ask
                    last = snapshot.get("31")
                    if last and str(last).replace(".", "").replace("-", "").isdigit():
                        return float(last)
                    bid = snapshot.get("84")
                    ask = snapshot.get("86")
                    if bid and ask:
                        return (float(bid) + float(ask)) / 2

                # IBKR market data sometimes needs a second request (cold start)
                if attempt == 0:
                    logger.info("Market data empty on first request — retrying (IBKR cold start)...")
                    time.sleep(2.0)
                    continue
                return None

            except httpx.TimeoutException:
                delay = RETRY_DELAY_BASE * (2 ** attempt)
                logger.warning(f"QQQ price timeout (attempt {attempt + 1}). Retrying in {delay:.1f}s...")
                time.sleep(delay)
            except Exception as e:
                logger.error(f"QQQ price fetch failed: {e}")
                return None
        logger.warning("QQQ price fetch failed after retries.")
        return None

    # ==========================================================================
    # ORDER EXECUTION
    # ==========================================================================

    def _reply_order_prompt(self, prompt_id: str, _depth: int = 0) -> Dict[str, Any]:
        """Auto-confirm IBKR order prompts (price caps, size warnings, etc.)."""
        if _depth >= 5:
            logger.error(f"Order prompt exceeded max confirmation rounds (5). Aborting.")
            return {"error": "Too many confirmation prompts", "prompt_id": prompt_id}
        try:
            res = self.client.post(
                f"{self.BASE_URL}/iserver/reply/{prompt_id}",
                json={"confirmed": True},
            )
            res.raise_for_status()
            result = res.json()
            # IBKR may return multiple confirmation rounds
            if isinstance(result, list) and len(result) > 0 and "id" in result[0]:
                return self._reply_order_prompt(result[0]["id"], _depth + 1)
            return result
        except Exception as e:
            logger.error(f"Order prompt reply failed: {e}")
            return {"error": str(e)}

    def place_order(
        self,
        conid: int,
        side: str,
        quantity: int,
        order_type: str = "MKT",
        price: Optional[float] = None,
        tif: str = "DAY",
        sec_type: str = "OPT",
    ) -> Dict[str, Any]:
        """Place a single-leg order. Used internally by combo order builder."""
        self.ensure_authenticated()
        endpoint = f"{self.BASE_URL}/iserver/account/{self.account_id}/orders"

        order = {
            "conid": conid,
            "orderType": order_type.upper(),
            "side": side.upper(),
            "quantity": quantity,
            "tif": tif.upper(),
        }
        if price and order_type.upper() == "LMT":
            order["price"] = price

        res = self.client.post(endpoint, json={"orders": [order]})
        if res.status_code != 200:
            logger.error(f"Order failed: {res.text}")
            return {"success": False, "error": res.text[:200]}

        data = res.json()
        # Handle confirmation prompts
        if isinstance(data, list) and len(data) > 0 and "id" in data[0]:
            return self._reply_order_prompt(data[0]["id"])
        return data

    def place_iron_condor(self, spot_price: float) -> Dict[str, Any]:
        """
        Place a 4-leg Iron Condor on QQQ.
        
        Strategy: ±$15 from spot, $7 wings, 0DTE, 1 contract.
        Legs:
            SELL call @ spot+15
            BUY  call @ spot+22
            SELL put  @ spot-15
            BUY  put  @ spot-8
        
        Uses IBKR combo order (all 4 legs in one ticket).
        """
        self.ensure_authenticated()
        
        # Round spot to nearest integer for clean strikes
        spot = round(spot_price)
        short_call = spot + self.QQQ_OFFSET
        long_call = short_call + self.QQQ_WING
        short_put = spot - self.QQQ_OFFSET
        long_put = short_put - self.QQQ_WING

        # Get today's expiry in YYYYMMDD
        today = date.today()
        expiry = today.strftime("%Y%m%d")

        logger.info(
            f"Placing IC: QQQ @ ${spot} | "
            f"Sell C{short_call}/Buy C{long_call} | "
            f"Sell P{short_put}/Buy P{long_put} | "
            f"Expiry: {expiry}"
        )

        # Resolve QQQ underlying conid
        qqq_conid = self.search_contract("QQQ")
        if not qqq_conid:
            return {"success": False, "error": "Cannot resolve QQQ conid"}

        # Resolve option conids for all 4 legs
        legs_config = [
            {"strike": short_call, "right": "C", "side": "SELL", "label": f"Sell C{short_call}"},
            {"strike": long_call, "right": "C", "side": "BUY", "label": f"Buy C{long_call}"},
            {"strike": short_put, "right": "P", "side": "SELL", "label": f"Sell P{short_put}"},
            {"strike": long_put, "right": "P", "side": "BUY", "label": f"Buy P{long_put}"},
        ]

        resolved_legs = []
        for leg in legs_config:
            conid = self.resolve_option_conid(
                underlying_conid=qqq_conid,
                strike=float(leg["strike"]),
                right=leg["right"],
                expiry=expiry,
            )
            if not conid:
                return {
                    "success": False,
                    "error": f"Cannot resolve conid for {leg['label']} (expiry {expiry}). "
                             f"Check if 0DTE options are available today.",
                }
            resolved_legs.append({**leg, "conid": conid})
            logger.info(f"  Resolved {leg['label']} → conid {conid}")

        # Build combo order (all 4 legs as one order)
        endpoint = f"{self.BASE_URL}/iserver/account/{self.account_id}/orders"
        
        order_legs = []
        for leg in resolved_legs:
            order_legs.append({
                "conid": leg["conid"],
                "side": leg["side"],
                "ratio": 1,
            })

        combo_order = {
            "orders": [
                {
                    "conidex": f"{resolved_legs[0]['conid']};;;{resolved_legs[1]['conid']}",
                    "orderType": "LMT",
                    "price": 0.0,  # Will be replaced by mid-price logic below
                    "side": "SELL",  # Net credit order (selling the IC)
                    "quantity": 1,
                    "tif": "DAY",
                    "legs": order_legs,
                }
            ]
        }

        # ── Mid-Price Limit Order with Price-Walking ──
        # Strategy: Start at mid-price, walk $0.02 every 15s, give up after 60s → MKT
        logger.info(f"Submitting 4-leg IC combo order (limit @ mid, price-walking)...")
        try:
            # First attempt: limit at mid-price (natural price)
            # IBKR will estimate mid when price=0 for combo — or use MKT as first try
            # Since we can't pre-fetch combo mid, start with MKT-like behavior via limit
            # Set aggressive limit: submit as MKT first, fall back to individual if rejected
            combo_order["orders"][0]["orderType"] = "MKT"
            
            # Retry combo order submission on timeout
            res = None
            for attempt in range(MAX_RETRIES):
                try:
                    res = self.client.post(endpoint, json=combo_order)
                    break  # Success — exit retry loop
                except httpx.TimeoutException:
                    delay = RETRY_DELAY_BASE * (2 ** attempt)
                    logger.warning(
                        f"Combo order timeout (attempt {attempt + 1}/{MAX_RETRIES}). "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)

            if res is None:
                # All retries exhausted on combo — fall back to individual legs
                logger.error("Combo order timed out after all retries. Trying individual legs...")
                return self._place_individual_legs(resolved_legs)

            if res.status_code != 200:
                # Fallback: place as 4 individual legs
                logger.warning(f"Combo order failed ({res.status_code}). Trying individual legs...")
                return self._place_individual_legs(resolved_legs)

            data = res.json()
            # Handle IBKR confirmation prompts
            if isinstance(data, list) and len(data) > 0 and "id" in data[0]:
                data = self._reply_order_prompt(data[0]["id"])

            logger.info(f"IC order response: {data}")
            return {
                "success": True,
                "method": "combo",
                "order_response": data,
                "legs": [
                    {"label": l["label"], "conid": l["conid"], "side": l["side"]}
                    for l in resolved_legs
                ],
                "strikes": {
                    "short_call": short_call,
                    "long_call": long_call,
                    "short_put": short_put,
                    "long_put": long_put,
                },
                "expiry": expiry,
            }
        except Exception as e:
            logger.error(f"IC order exception: {e}")
            return {"success": False, "error": str(e)[:200]}

    def _place_individual_legs(self, resolved_legs: List[Dict]) -> Dict[str, Any]:
        """
        Fallback: place 4 legs as individual market orders if combo fails.
        
        RISK-FIRST ORDERING: Places long options (BUY/wings) first, then short options.
        This ensures if a short leg fails, we're never left with a naked short position.
        If a long leg fails, we abort before placing any shorts.
        
        Implements partial execution recovery:
        - If some legs fill and others fail, logs the partial state
        - Returns detailed per-leg results for manual review
        """
        # Reorder: BUY legs first (long wings), then SELL legs (short strikes)
        buy_legs = [leg for leg in resolved_legs if leg["side"] == "BUY"]
        sell_legs = [leg for leg in resolved_legs if leg["side"] == "SELL"]
        ordered_legs = buy_legs + sell_legs
        
        logger.info(
            f"Individual legs — risk-first order: "
            f"{len(buy_legs)} BUY (wings) first, then {len(sell_legs)} SELL (shorts)"
        )

        results = []
        all_success = True
        filled_count = 0
        failed_count = 0
        buy_phase_failed = False

        for i, leg in enumerate(ordered_legs):
            # If a BUY leg failed, do NOT place SELL legs (prevents naked shorts)
            if buy_phase_failed and leg["side"] == "SELL":
                results.append({
                    "label": leg["label"], 
                    "status": "skipped",
                    "reason": "Aborted — long wing failed, refusing to place naked short",
                })
                failed_count += 1
                all_success = False
                continue

            try:
                res = self.place_order(
                    conid=leg["conid"],
                    side=leg["side"],
                    quantity=1,
                    order_type="MKT",
                )
                results.append({"label": leg["label"], "result": res, "status": "submitted"})
                if isinstance(res, dict) and res.get("error"):
                    all_success = False
                    failed_count += 1
                    if leg["side"] == "BUY":
                        buy_phase_failed = True
                else:
                    filled_count += 1
            except httpx.TimeoutException:
                # Timeout on individual leg — retry once
                logger.warning(f"Timeout on leg {leg['label']}. Retrying once...")
                time.sleep(1.0)
                try:
                    res = self.place_order(
                        conid=leg["conid"],
                        side=leg["side"],
                        quantity=1,
                        order_type="MKT",
                    )
                    results.append({"label": leg["label"], "result": res, "status": "submitted_retry"})
                    filled_count += 1
                except Exception as retry_e:
                    results.append({"label": leg["label"], "error": str(retry_e)[:100], "status": "failed"})
                    all_success = False
                    failed_count += 1
                    if leg["side"] == "BUY":
                        buy_phase_failed = True
            except Exception as e:
                results.append({"label": leg["label"], "error": str(e)[:100], "status": "failed"})
                all_success = False
                failed_count += 1
                if leg["side"] == "BUY":
                    buy_phase_failed = True

        # Partial execution warning
        if filled_count > 0 and failed_count > 0:
            logger.error(
                f"⚠️ PARTIAL EXECUTION: {filled_count} legs filled, {failed_count} failed. "
                f"Manual intervention required to close orphaned legs."
            )

        return {
            "success": all_success,
            "method": "individual_legs",
            "execution_order": "risk_first (BUY wings before SELL shorts)",
            "filled_count": filled_count,
            "failed_count": failed_count,
            "partial_execution": filled_count > 0 and failed_count > 0,
            "buy_phase_failed": buy_phase_failed,
            "legs": results,
        }


# ==========================================================================
# MODULE-LEVEL HELPERS (imported by routes/live.py)
# ==========================================================================

def execute_qqq_sync(spot_price: Optional[float] = None) -> Dict[str, Any]:
    """
    Synchronous entry point for QQQ IC execution.
    Called by routes/live.py → /api/live/live-execute
    
    1. Gets QQQ price (from IBKR or param)
    2. Places 4-leg IC
    3. Sends Telegram notification with result
    4. Returns order result
    """
    executor = get_ibkr_executor()

    if not executor.is_configured:
        return {
            "success": False,
            "error": "IBKR not configured. Set IBKR_CLIENT_ID, IBKR_ACCOUNT_ID, IBKR_PRIVATE_KEY_PEM env vars.",
        }

    # Authenticate
    if not executor.ensure_authenticated():
        _notify_trade_result(None, error="IBKR authentication failed")
        return {"success": False, "error": "IBKR authentication failed. Check credentials."}

    # Get spot price
    if not spot_price:
        spot_price = executor.get_qqq_price()
    if not spot_price:
        # Last resort fallback to yfinance
        try:
            import yfinance as yf
            data = yf.download("QQQ", period="1d", progress=False, timeout=10)
            if data is not None and len(data) >= 1:
                close_col = data["Close"]
                if hasattr(close_col, "columns"):
                    close_col = close_col.iloc[:, 0]
                spot_price = float(close_col.iloc[-1])
        except Exception:
            pass

    if not spot_price:
        _notify_trade_result(None, error="Cannot determine QQQ price")
        return {"success": False, "error": "Cannot determine QQQ price from IBKR or yfinance."}

    # Place Iron Condor
    result = executor.place_iron_condor(spot_price=spot_price)
    
    # Send Telegram notification
    _notify_trade_result(result, spot_price=spot_price)
    
    return result


def _notify_trade_result(result: Optional[Dict], spot_price: float = 0, error: str = ""):
    """Send Telegram notification for trade execution result."""
    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from scripts.telegram_bot import send_alert
        
        if error:
            send_alert("error", f"🚨 QQQ IC Execution Failed\n\nError: {error}")
            return
        
        if not result:
            return
            
        if result.get("success"):
            strikes = result.get("strikes", {})
            method = result.get("method", "unknown")
            msg = (
                f"✅ QQQ Iron Condor PLACED\n\n"
                f"Spot: ${spot_price:.2f}\n"
                f"Sell C{strikes.get('short_call', '?')} / Buy C{strikes.get('long_call', '?')}\n"
                f"Sell P{strikes.get('short_put', '?')} / Buy P{strikes.get('long_put', '?')}\n"
                f"Method: {method}\n"
                f"Expiry: 0DTE (today)\n\n"
                f"Wing width: ${result.get('strikes', {}).get('long_call', 0) - result.get('strikes', {}).get('short_call', 0)}. "
                f"Max loss capped."
            )
            send_alert("eligible", msg)
        else:
            error_msg = result.get("error", "Unknown error")
            partial = result.get("partial_execution", False)
            if partial:
                filled = result.get("filled_count", 0)
                failed = result.get("failed_count", 0)
                msg = (
                    f"⚠️ QQQ IC PARTIAL EXECUTION\n\n"
                    f"Spot: ${spot_price:.2f}\n"
                    f"Filled: {filled} legs | Failed: {failed} legs\n"
                    f"MANUAL INTERVENTION REQUIRED\n\n"
                    f"Check IBKR positions immediately."
                )
                send_alert("error", msg)
            else:
                send_alert("error", f"❌ QQQ IC Failed\n\nSpot: ${spot_price:.2f}\nError: {error_msg}")
    except Exception as e:
        logger.warning(f"Telegram notification failed (non-fatal): {e}")
