from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import pytz
from config import settings
from .base import BaseBroker

IST = pytz.timezone("Asia/Kolkata")

# Fyers interval mapping
INTERVAL_MAP = {
    "minute":   "1",
    "5minute":  "5",
    "15minute": "15",
    "30minute": "30",
    "60minute": "60",
    "day":      "D",
    "week":     "W",
    "month":    "M",
}


def _fyers_symbol(symbol: str, exchange: str = "NSE") -> str:
    """Convert NSE:RELIANCE -> NSE:RELIANCE-EQ for Fyers."""
    symbol = symbol.upper().strip()
    if "-EQ" not in symbol and "-BE" not in symbol:
        symbol = f"{symbol}-EQ"
    return f"{exchange}:{symbol}"


class FyersBroker(BaseBroker):

    def _client(self):
        try:
            from fyers_apiv3 import fyersModel
        except ImportError:
            raise ImportError("fyers-apiv3 not installed. Run: pip install fyers-apiv3")
        if not settings.is_fyers_authenticated():
            raise ValueError("Fyers access token not set.")
        return fyersModel.FyersModel(
            client_id=settings.FYERS_APP_ID,
            is_async=False,
            token=settings.get_fyers_token(),
            log_path="",
        )

    def is_authenticated(self) -> bool:
        return settings.is_fyers_authenticated()

    def get_instrument_token(self, symbol: str, exchange: str = "NSE") -> Tuple[str, str]:
        fyers_sym = _fyers_symbol(symbol, exchange)
        fyers = self._client()
        resp = fyers.quotes(data={"symbols": fyers_sym})
        if resp.get("s") != "ok":
            raise ValueError(f"Fyers: symbol '{symbol}' not found: {resp}")
        d = resp["d"][0]["v"]
        return fyers_sym, d.get("short_name", symbol)

    def fetch_historical(self, instrument_key: str, interval: str, days_back: int) -> List[Dict]:
        fyers = self._client()
        to_dt = datetime.now(IST)
        from_dt = to_dt - timedelta(days=days_back)
        fyers_interval = INTERVAL_MAP.get(interval, interval)

        resp = fyers.history(data={
            "symbol": instrument_key,
            "resolution": fyers_interval,
            "date_format": "1",
            "range_from": from_dt.strftime("%Y-%m-%d"),
            "range_to": to_dt.strftime("%Y-%m-%d"),
            "cont_flag": "1",
        })
        if resp.get("s") != "ok":
            raise ValueError(f"Fyers history error: {resp}")

        candles = []
        for c in resp.get("candles", []):
            # c = [epoch, open, high, low, close, volume]
            dt = datetime.fromtimestamp(c[0], tz=IST)
            candles.append({
                "date": dt,
                "open": c[1],
                "high": c[2],
                "low": c[3],
                "close": c[4],
                "volume": c[5],
            })
        return candles

    def fetch_ltp(self, symbol: str, exchange: str = "NSE") -> float:
        fyers = self._client()
        fyers_sym = _fyers_symbol(symbol, exchange)
        resp = fyers.quotes(data={"symbols": fyers_sym})
        if resp.get("s") != "ok":
            raise ValueError(f"Fyers LTP error: {resp}")
        return float(resp["d"][0]["v"]["lp"])

    def place_order(
        self,
        symbol: str,
        transaction_type: str,
        quantity: int,
        order_type: str = "MARKET",
        price: float = 0.0,
        trigger_price: float = 0.0,
        product: str = "CNC",
        exchange: str = "NSE",
    ) -> Optional[Dict]:
        fyers = self._client()
        fyers_sym = _fyers_symbol(symbol, exchange)

        order_type_map = {"MARKET": 2, "LIMIT": 1, "SL": 4, "SL-M": 3}
        product_map = {"CNC": "CNC", "MIS": "INTRADAY", "NRML": "MARGIN"}
        side = 1 if transaction_type == "BUY" else -1

        resp = fyers.place_order(data={
            "symbol": fyers_sym,
            "qty": quantity,
            "type": order_type_map.get(order_type, 2),
            "side": side,
            "productType": product_map.get(product, "CNC"),
            "limitPrice": price,
            "stopPrice": trigger_price,
            "validity": "DAY",
            "disclosedQty": 0,
            "offlineOrder": False,
            "stopLoss": 0,
            "takeProfit": 0,
        })
        if resp.get("s") != "ok":
            raise ValueError(f"Fyers order failed: {resp}")
        return {"order_id": resp["id"], "broker": "fyers"}

    def cancel_order(self, order_id: str) -> bool:
        fyers = self._client()
        resp = fyers.cancel_order(data={"id": order_id})
        return resp.get("s") == "ok"

    def get_positions(self) -> List[Dict]:
        fyers = self._client()
        resp = fyers.positions()
        return resp.get("netPositions", [])

    def get_orders(self) -> List[Dict]:
        fyers = self._client()
        resp = fyers.orderbook()
        return resp.get("orderBook", [])
