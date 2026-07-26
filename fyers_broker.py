""
FyersBroker - Live broker using Fyers API v3 (pure requests, no SDK dependency)
Matches PaperBroker interface for drop-in replacement.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
import requests
from datetime import datetime, time as dt_time, date, timedelta
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode

logger = logging.getLogger("fyers_broker")

# ── Fyers API constants ──────────────────────────────────────────────────────
FYERS_BASE_URL = "https://api-t1.fyers.in/api/v3"
FYERS_AUTH_URL = "https://api-t1.fyers.in/api/v3"
FYERS_OTP_URL = "https://api-t1.fyers.in/api/v3"
FYERS_TOKEN_URL = f"{FYERS_AUTH_URL}/token"
FYERS_PROFILE_URL = f"{FYERS_BASE_URL}/profile"
FYERS_FUNDS_URL = f"{FYERS_BASE_URL}/funds"
FYERS_ORDERS_URL = f"{FYERS_BASE_URL}/orders"
FYERS_POSITIONS_URL = f"{FYERS_BASE_URL}/positions"
FYERS_QUOTES_URL = f"{FYERS_BASE_URL}/quotes"
FYERS_VALIDATE_URL = f"{FYERS_BASE_URL}/validate/access-token"

# NFO lot sizes
LOT_SIZES = {"NIFTY": 25, "BANKNIFTY": 15, "FINNIFTY": 25}

# Order type constants
ORDER_TYPE_MARKET = 1
ORDER_TYPE_LIMIT = 2
ORDER_TYPE_SL = 3
ORDER_TYPE_SL_MARKET = 4

# Side constants
SIDE_BUY = 1
SIDE_SELL = -1

# Product type
PRODUCT_INTRADAY = "INTRADAY"
PRODUCT_CARRYFORWARD = "CARRYFORWARD"


def _build_option_symbol(
    underlying: str,
    strike: int,
    option_type: str,  # "CE" or "PE"
    expiry: Optional[date] = None,
) -> str:
    """Build Fyers symbol string like NFO:NIFTY2472524400CE"""
    if expiry is None:
        # Default to nearest Thursday expiry
        today = date.today()
        days_ahead = (3 - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        expiry = today + timedelta(days=days_ahead)
    # Fyers expiry format: YYMMDD, then 5-digit strike
    exp_str = expiry.strftime("%y%m%d")
    strike_str = str(strike).zfill(5)
    return f"NFO:{underlying}{exp_str}{strike_str}{option_type}"


class FyersAuthError(Exception):
    pass


class FyersOrderError(Exception):
    pass


class FyersAPIError(Exception):
    pass


class FyersBroker:
    """
    Live broker using Fyers API v3.
    Matches PaperBroker interface for drop-in replacement.
    Uses pure requests - no fyers-apiv3 SDK needed.
    """

    def __init__(
        self,
        capital: float = 1_000_000,
        lot_size: int = 25,
        slippage_pct: float = 0.001,
        app_id: Optional[str] = None,
        secret_key: Optional[str] = None,
        access_token: Optional[str] = None,
        redirect_uri: str = "https://www.google.com",
    ):
        self.capital = capital
        self.lot_size = lot_size
        self.slippage_pct = slippage_pct

        # Fyers credentials
        self.app_id = app_id or ""
        self.secret_key = secret_key or ""
        self.access_token = access_token or ""
        self.redirect_uri = redirect_uri

        # Local state
        self._positions: Dict[str, Dict] = {}  # symbol -> position info
        self._fills: List[Dict] = []
        self._market_data: Dict[str, Any] = {}
        self._is_connected = False
        self._profile: Dict = {}
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    # ── Auth ──────────────────────────────────────────────────────────────

    @property
    def is_authenticated(self) -> bool:
        return bool(self.access_token and self.app_id)

    def _auth_headers(self) -> Dict[str, str]:
        """Return headers with Fyers authorization."""
        if not self.access_token:
            raise FyersAuthError("Not authenticated. Set access_token first.")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def generate_auth_url(self, state: str = "kiwi_bot") -> str:
        """Generate the OAuth authorization URL for the user to visit."""
        if not self.app_id:
            raise FyersAuthError("App ID not set")
        params = {
            "client_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "state": state,
        }
        return f"https://api-t1.fyers.in/api/v3/generate-authcode?{urlencode(params)}"

    def generate_token(self, auth_code: str) -> Dict[str, Any]:
        """
        Exchange auth_code (from OAuth callback) for access_token.
        Returns the full API response dict.
        """
        if not self.app_id or not self.secret_key:
            raise FyersAuthError("App ID and Secret Key required")

        payload = {
            "grant_type": "authorization_code",
            "appId": self.app_id,
            "secretKey": self.secret_key,
            "auth_code": auth_code,
            "redirect_uri": self.redirect_uri,
        }

        try:
            resp = self._session.post(FYERS_TOKEN_URL, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise FyersAPIError(f"Token request failed: {e}") from e

        if data.get("s") != "ok":
            raise FyersAuthError(f"Token generation failed: {data}")

        self.access_token = data.get("access_token", "")
        self._is_connected = True
        logger.info("Fyers access token obtained successfully")
        return data

    def validate_token(self) -> bool:
        """Check if the current access_token is still valid."""
        if not self.access_token:
            return False
        try:
            resp = self._session.post(
                FYERS_VALIDATE_URL,
                headers=self._auth_headers(),
                timeout=10,
            )
            data = resp.json()
            return data.get("s") == "ok"
        except Exception:
            return False

    def get_profile(self) -> Dict[str, Any]:
        """Fetch account profile info."""
        try:
            resp = self._session.get(
                FYERS_PROFILE_URL,
                headers=self._auth_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("s") == "ok":
                self._profile = data.get("data", {})
            return data
        except requests.RequestException as e:
            raise FyersAPIError(f"Profile fetch failed: {e}") from e

    def get_funds(self) -> Dict[str, Any]:
        """Fetch available margin/funds."""
        try:
            resp = self._session.get(
                FYERS_FUNDS_URL,
                headers=self._auth_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            raise FyersAPIError(f"Funds fetch failed: {e}") from e

    # ── Symbol helpers ────────────────────────────────────────────────────

    def get_ltp(self, symbols: List[str]) -> Dict[str, float]:
        """
        Fetch LTP for given Fyers symbols.
        symbols: ["NSE:NIFTY24400CE", ...]
        Returns: {"NSE:NIFTY24400CE": 245.50, ...}
        """
        if not symbols:
            return {}
        try:
            payload = {"symbols": ",".join(symbols)}
            resp = self._session.post(
                FYERS_QUOTES_URL,
                headers=self._auth_headers(),
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            result = {}
            if data.get("s") == "ok":
                for sym in symbols:
                    quote = data.get("d", {}).get(sym, {})
                    result[sym] = quote.get("v", {}).get("lp", 0.0)
            return result
        except requests.RequestException as e:
            logger.error(f"LTP fetch failed: {e}")
            return {}

    def search_symbol(self, query: str, exchange: str = "NFO") -> List[Dict]:
        """
        Search for symbols. Not a full Fyers API endpoint -
        we use quotes API with a partial symbol.
        """
        try:
            symbol = f"{exchange}:{query}"
            payload = {"symbols": symbol}
            resp = self._session.post(
                FYERS_QUOTES_URL,
                headers=self._auth_headers(),
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            if data.get("s") == "ok":
                for sym, info in data.get("d", {}).items():
                    results.append({"symbol": sym, **info.get("v", {})})
            return results
        except Exception as e:
            logger.error(f"Symbol search failed: {e}")
            return []

    # ── Order placement (PaperBroker interface) ───────────────────────────

    async def place_order(
        self,
        signal,
        underlying: str,
        timestamp: datetime,
        qty: Optional[int] = None,
    ) -> Optional[Dict]:
        """
        Place a real order on Fyers.
        signal: Signal object with .action, .option_type, .strike, .entry_price, .sl, .target
        underlying: e.g. "NIFTY", "BANKNIFTY"
        timestamp: order timestamp
        qty: override quantity (default: lot_size)
        Returns: Dict with fill info (matching SimulatedPosition shape) or None
        """
        if not self.is_authenticated:
            logger.error("Cannot place order - not authenticated")
            return None

        try:
            # Build Fyers symbol
            option_suffix = "CE" if signal.option_type.value == "CE" else "PE"
            fyers_symbol = _build_option_symbol(
                underlying, signal.strike, option_suffix
            )

            # Determine side
            side = SIDE_BUY if signal.action.value == "BUY" else SIDE_SELL

            # Quantity
            actual_qty = qty or self.lot_size

            # Place MARKET order
            order_payload = {
                "symbol": fyers_symbol,
                "qty": actual_qty,
                "type": ORDER_TYPE_MARKET,
                "side": side,
                "productType": PRODUCT_INTRADAY,
                "limitPrice": 0,
                "stopPrice": 0,
                "validity": "DAY",
                "disclosedQty": 0,
                "offlineOrder": False,
                "orderTag": f"kiwi_{int(time.time())}",
            }

            logger.info(
                f"Placing order: {fyers_symbol} side={'BUY' if side==1 else 'SELL'} "
                f"qty={actual_qty} type=MARKET"
            )

            resp = self._session.post(
                FYERS_ORDERS_URL,
                headers=self._auth_headers(),
                json=order_payload,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("s") != "ok":
                logger.error(f"Order rejected: {data}")
                return None

            order_id = data.get("id", "")
            logger.info(f"Order placed: id={order_id}")

            # Fetch order details to get fill price
            fill_info = await self._get_order_fill(order_id, fyers_symbol)
            if fill_info is None:
                fill_info = {
                    "symbol": fyers_symbol,
                    "entry_price": signal.entry_price,
                    "qty": actual_qty,
                    "side": "BUY" if side == SIDE_BUY else "SELL",
                    "order_id": order_id,
                }

            # Track locally
            self._positions[fyers_symbol] = {
                "symbol": fyers_symbol,
                "underlying": underlying,
                "option_type": option_suffix,
                "strike": signal.strike,
                "entry_price": fill_info.get("entry_price", 0),
                "qty": actual_qty,
                "side": fill_info.get("side", "BUY"),
                "sl": signal.sl,
                "target": signal.target,
                "order_id": order_id,
                "entry_time": timestamp.isoformat(),
            }
            self._fills.append(self._positions[fyers_symbol])

            return self._positions[fyers_symbol]

        except Exception as e:
            logger.error(f"place_order exception: {e}")
            return None

    async def _get_order_fill(self, order_id: str, symbol: str) -> Optional[Dict]:
        """Poll for order fill details."""
        for _ in range(5):
            try:
                resp = self._session.get(
                    f"{FYERS_ORDERS_URL}?order_id={order_id}",
                    headers=self._auth_headers(),
                    timeout=10,
                )
                data = resp.json()
                if data.get("s") == "ok":
                    orders = data.get("data", {}).get("orderBook", [])
                    for o in orders:
                        if o.get("id") == order_id:
                            return {
                                "symbol": symbol,
                                "entry_price": float(o.get("tradedPrice", 0))
                                if o.get("tradedPrice", 0) > 0
                                else 0.0,
                                "qty": o.get("qty", 0),
                                "side": "BUY" if o.get("side") == 1 else "SELL",
                                "order_id": order_id,
                                "status": o.get("status", ""),
                            }
            except Exception:
                pass
            await asyncio.sleep(0.5)
        return None

    # ── Price updates (PaperBroker interface) ─────────────────────────────

    async def update_prices(self, underlying_spot: float, timestamp: datetime) -> None:
        """
        Fetch real LTPs for all open positions from Fyers.
        underlying_spot: current spot price (for reference)
        """
        if not self._positions:
            return

        symbols = list(self._positions.keys())
        ltps = self.get_ltp(symbols)

        for sym, pos in self._positions.items():
            ltp = ltps.get(sym, 0)
            if ltp > 0:
                pos["current_price"] = ltp
                entry = pos.get("entry_price", 0)
                qty = pos.get("qty", 0)
                if pos.get("side") == "BUY":
                    pos["pnl"] = (ltp - entry) * qty
                else:
                    pos["pnl"] = (entry - ltp) * qty
                pos["pnl_pct"] = (
                    (pos["pnl"] / (entry * qty)) * 100 if entry * qty > 0 else 0
                )

    # ── Square off (PaperBroker interface) ────────────────────────────────

    async def square_off_all(self, timestamp: datetime) -> List[Dict]:
        """Close all open positions by placing opposite orders."""
        if not self._positions:
            return []

        closed = []
        for sym, pos in list(self._positions.items()):
            try:
                # Opposite side of current position
                close_side = SIDE_SELL if pos.get("side") == "BUY" else SIDE_BUY

                order_payload = {
                    "symbol": sym,
                    "qty": pos.get("qty", self.lot_size),
                    "type": ORDER_TYPE_MARKET,
                    "side": close_side,
                    "productType": PRODUCT_INTRADAY,
                    "limitPrice": 0,
                    "stopPrice": 0,
                    "validity": "DAY",
                    "disclosedQty": 0,
                    "offlineOrder": False,
                    "orderTag": f"kiwi_sq_{int(time.time())}",
                }

                resp = self._session.post(
                    FYERS_ORDERS_URL,
                    headers=self._auth_headers(),
                    json=order_payload,
                    timeout=15,
                )
                data = resp.json()

                if data.get("s") == "ok":
                    pos["exit_time"] = timestamp.isoformat()
                    pos["exit_order_id"] = data.get("id", "")
                    closed.append(pos)
                    logger.info(f"Squared off {sym}: order_id={data.get('id')}")
                else:
                    logger.error(f"Square-off failed for {sym}: {data}")

            except Exception as e:
                logger.error(f"square_off error for {sym}: {e}")

        self._positions.clear()
        return closed

    # ── Market data (PaperBroker interface) ───────────────────────────────

    async def update_market_data(
        self,
        pcr=None,
        max_pain=None,
        oi_buildup=None,
        iv_percentile=None,
    ) -> None:
        """Store market data for display/reference."""
        self._market_data.update({
            "pcr": pcr,
            "max_pain": max_pain,
            "oi_buildup": oi_buildup,
            "iv_percentile": iv_percentile,
            "updated_at": datetime.now().isoformat(),
        })

    # ── Portfolio summary (PaperBroker interface) ─────────────────────────

    def get_portfolio_summary(self) -> Dict:
        """
        Return portfolio summary. Pulls real funds from Fyers if authenticated.
        """
        total_pnl = sum(p.get("pnl", 0) for p in self._positions.values())
        invested = sum(
            p.get("entry_price", 0) * p.get("qty", 0)
            for p in self._positions.values()
        )

        summary = {
            "broker": "Fyers (LIVE)",
            "authenticated": self.is_authenticated,
            "connected": self._is_connected,
            "open_positions": len(self._positions),
            "total_pnl": round(total_pnl, 2),
            "invested": round(invested, 2),
            "capital": self.capital,
            "available_margin": None,
            "market_data": self._market_data,
            "profile": self._profile,
        }

        # Try to get real funds
        if self.is_authenticated:
            try:
                funds_data = self.get_funds()
                if funds_data.get("s") == "ok":
                    fund_info = funds_data.get("data", {})
                    # equity intraday or commodity margin
                    limits = fund_info.get("equity", {}).get("intraday_payin", 0)
                    if not limits:
                        limits = (
                            fund_info.get("commodity", {}).get("intraday_payin", 0)
                        )
                    summary["available_margin"] = limits
                    summary["capital"] = limits or self.capital
            except Exception as e:
                logger.warning(f"Could not fetch funds: {e}")

        return summary

    # ── Positions (PaperBroker interface) ─────────────────────────────────

    def get_positions(self) -> List[Dict]:
        """Return list of open positions."""
        return list(self._positions.values())

    def get_fyers_positions(self) -> Dict[str, Any]:
        """Fetch real positions from Fyers API."""
        if not self.is_authenticated:
            return {"error": "Not authenticated"}
        try:
            resp = self._session.get(
                FYERS_POSITIONS_URL,
                headers=self._auth_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            return {"error": str(e)}

    def get_orders(self) -> Dict[str, Any]:
        """Fetch order history from Fyers API."""
        if not self.is_authenticated:
            return {"error": "Not authenticated"}
        try:
            resp = self._session.get(
                FYERS_ORDERS_URL,
                headers=self._auth_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            return {"error": str(e)}

    # ── Reset (PaperBroker interface) ─────────────────────────────────────

    def reset(self) -> None:
        """Clear all local state (does NOT close Fyers positions)."""
        self._positions.clear()
        self._fills.clear()
        self._market_data.clear()
        self._profile.clear()
        logger.info("FyersBroker local state reset")

    def configure(self, app_id: str, secret_key: str, redirect_uri: str = ""):
        """Set Fyers credentials."""
        self.app_id = app_id
        self.secret_key = secret_key
        if redirect_uri:
            self.redirect_uri = redirect_uri
        logger.info(f"Fyers configured with app_id={app_id[:6]}...")

    def set_access_token(self, token: str):
        """Set access token directly (e.g., from stored credentials)."""
        self.access_token = token
        self._is_connected = bool(token)
        logger.info("Access token set")


# ── Standalone test ───────────────────────────────────────────────────────
if __name__ == "__main__":
    broker = FyersBroker()
    print("FyersBroker initialized (no SDK dependency)")
    print(f"Symbol example: {_build_option_symbol('NIFTY', 24000, 'CE')}")
    print("Configure with app_id + secret_key, then generate_auth_url()")
