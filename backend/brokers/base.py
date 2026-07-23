from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple


class BaseBroker(ABC):
    """Abstract broker interface — both Zerodha and Fyers implement this."""

    @abstractmethod
    def is_authenticated(self) -> bool: ...

    @abstractmethod
    def get_instrument_token(self, symbol: str, exchange: str = "NSE") -> Tuple[str, str]:
        """Returns (token_or_symbol_key, company_name)."""
        ...

    @abstractmethod
    def fetch_historical(
        self,
        instrument_key: str,
        interval: str,           # "minute", "5minute", "15minute", "day", "week", "month"
        days_back: int,
    ) -> List[Dict]:
        """Returns list of OHLCV dicts with keys: date, open, high, low, close, volume."""
        ...

    @abstractmethod
    def fetch_ltp(self, symbol: str, exchange: str = "NSE") -> float:
        """Fetch latest traded price."""
        ...

    @abstractmethod
    def get_available_funds(self) -> float:
        """Returns available cash/margin for equity trading, in INR."""
        ...

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        transaction_type: str,   # "BUY" | "SELL"
        quantity: int,
        order_type: str,         # "MARKET" | "LIMIT" | "SL" | "SL-M"
        price: float = 0.0,
        trigger_price: float = 0.0,
        product: str = "CNC",    # "CNC" | "MIS" | "NRML"
        exchange: str = "NSE",
    ) -> Optional[Dict]:
        """Place an order. Returns order dict with 'order_id' on success."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    def get_positions(self) -> List[Dict]: ...

    @abstractmethod
    def get_orders(self) -> List[Dict]: ...

    def ohlcv_to_candles(self, data: List[Dict]) -> List[Dict]:
        """Normalise broker-specific OHLCV to standard candle format."""
        candles = []
        for row in data:
            date = row.get("date", row.get("datetime", ""))
            if hasattr(date, "strftime"):
                date_str = date.strftime("%Y-%m-%d %H:%M:%S") if hasattr(date, "hour") else date.strftime("%Y-%m-%d")
            else:
                date_str = str(date)[:19]
            candles.append({
                "date": date_str,
                "open": round(float(row["open"]), 2),
                "high": round(float(row["high"]), 2),
                "low": round(float(row["low"]), 2),
                "close": round(float(row["close"]), 2),
                "volume": int(row["volume"]),
            })
        return candles
