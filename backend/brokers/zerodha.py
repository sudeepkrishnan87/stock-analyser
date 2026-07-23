from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import pytz
from kiteconnect import KiteConnect
from config import settings
from .base import BaseBroker

IST = pytz.timezone("Asia/Kolkata")

_instruments_cache: Dict[str, Dict] = {}
_instruments_loaded: bool = False

INTERVAL_MAP = {
    "minute":   "minute",
    "5minute":  "5minute",
    "15minute": "15minute",
    "30minute": "30minute",
    "60minute": "60minute",
    "day":      "day",
    "week":     "week",
    # "month" is not a valid Kite interval — handled separately via daily resample
}


class ZerodhaBroker(BaseBroker):

    def _client(self) -> KiteConnect:
        if not settings.is_authenticated():
            raise ValueError("Zerodha access token not set.")
        kite = KiteConnect(api_key=settings.KITE_API_KEY)
        kite.set_access_token(settings.get_access_token())
        return kite

    def _load_instruments(self, kite: KiteConnect):
        global _instruments_cache, _instruments_loaded
        if _instruments_loaded:
            return
        for inst in kite.instruments("NSE"):
            _instruments_cache[inst["tradingsymbol"]] = {
                "instrument_token": inst["instrument_token"],
                "name": inst["name"],
                "exchange": inst["exchange"],
            }
        for inst in kite.instruments("BSE"):
            key = f"BSE:{inst['tradingsymbol']}"
            _instruments_cache[key] = {
                "instrument_token": inst["instrument_token"],
                "name": inst["name"],
                "exchange": "BSE",
            }
        _instruments_loaded = True

    def is_authenticated(self) -> bool:
        return settings.is_authenticated()

    def get_instrument_token(self, symbol: str, exchange: str = "NSE") -> Tuple[str, str]:
        kite = self._client()
        self._load_instruments(kite)
        symbol = symbol.upper().strip().replace(".NS", "").replace(".BO", "")
        if symbol not in _instruments_cache:
            raise ValueError(f"Symbol '{symbol}' not found on NSE.")
        info = _instruments_cache[symbol]
        return str(info["instrument_token"]), info["name"]

    def fetch_historical(self, instrument_key: str, interval: str, days_back: int) -> List[Dict]:
        kite = self._client()
        to_date = datetime.now(IST)

        if interval == "month":
            return self._fetch_monthly(kite, instrument_key, days_back)

        from_date = to_date - timedelta(days=days_back)
        kite_interval = INTERVAL_MAP.get(interval, interval)
        data = kite.historical_data(
            instrument_token=int(instrument_key),
            from_date=from_date.strftime("%Y-%m-%d %H:%M:%S"),
            to_date=to_date.strftime("%Y-%m-%d %H:%M:%S"),
            interval=kite_interval,
        )
        return data

    def _fetch_monthly(self, kite: KiteConnect, instrument_key: str, days_back: int) -> List[Dict]:
        """Kite has no monthly interval — fetch daily and resample to calendar months."""
        import pandas as pd
        to_date = datetime.now(IST)
        from_date = to_date - timedelta(days=days_back)
        daily = kite.historical_data(
            instrument_token=int(instrument_key),
            from_date=from_date.strftime("%Y-%m-%d %H:%M:%S"),
            to_date=to_date.strftime("%Y-%m-%d %H:%M:%S"),
            interval="day",
        )
        if not daily:
            return []
        df = pd.DataFrame(daily)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        monthly = df.resample("ME").agg({
            "open":   "first",
            "high":   "max",
            "low":    "min",
            "close":  "last",
            "volume": "sum",
        }).dropna()
        monthly = monthly.reset_index()
        return monthly.to_dict(orient="records")

    def fetch_ltp(self, symbol: str, exchange: str = "NSE") -> float:
        kite = self._client()
        quote = kite.ltp([f"{exchange}:{symbol}"])
        return float(quote[f"{exchange}:{symbol}"]["last_price"])

    def get_available_funds(self) -> float:
        kite = self._client()
        equity = kite.margins().get("equity", {})
        # "net" = cash + collateral - utilised — the actual tradable margin
        # right now. Fall back to live_balance if a given account's response
        # shape omits "net".
        net = equity.get("net")
        if net is not None:
            return float(net)
        return float(equity.get("available", {}).get("live_balance", 0))

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
        kite = self._client()
        kite_order_type = {
            "MARKET": kite.ORDER_TYPE_MARKET,
            "LIMIT": kite.ORDER_TYPE_LIMIT,
            "SL": kite.ORDER_TYPE_SL,
            "SL-M": kite.ORDER_TYPE_SLM,
        }.get(order_type, kite.ORDER_TYPE_MARKET)

        kite_product = {
            "CNC": kite.PRODUCT_CNC,
            "MIS": kite.PRODUCT_MIS,
            "NRML": kite.PRODUCT_NRML,
        }.get(product, kite.PRODUCT_CNC)

        kite_tx = kite.TRANSACTION_TYPE_BUY if transaction_type == "BUY" else kite.TRANSACTION_TYPE_SELL

        order_id = kite.place_order(
            tradingsymbol=symbol,
            exchange=exchange,
            transaction_type=kite_tx,
            quantity=quantity,
            order_type=kite_order_type,
            product=kite_product,
            price=price if order_type == "LIMIT" else None,
            trigger_price=trigger_price if order_type in ("SL", "SL-M") else None,
            variety=kite.VARIETY_REGULAR,
        )
        return {"order_id": order_id, "broker": "zerodha"}

    def cancel_order(self, order_id: str) -> bool:
        kite = self._client()
        kite.cancel_order(variety=kite.VARIETY_REGULAR, order_id=order_id)
        return True

    def get_positions(self) -> List[Dict]:
        kite = self._client()
        pos = kite.positions()
        return pos.get("net", [])

    def get_orders(self) -> List[Dict]:
        kite = self._client()
        return kite.orders()
