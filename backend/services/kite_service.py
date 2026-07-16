from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import pytz
from kiteconnect import KiteConnect
from config import settings

IST = pytz.timezone("Asia/Kolkata")

# In-memory instrument cache (avoids repeated API calls)
_instruments_cache: Dict[str, Dict] = {}
_instruments_loaded: bool = False


def get_kite_client() -> KiteConnect:
    if not settings.is_authenticated():
        raise ValueError("Kite access token not set. Please set it via /api/auth/token.")
    kite = KiteConnect(api_key=settings.KITE_API_KEY)
    kite.set_access_token(settings.get_access_token())
    return kite


def load_instruments(kite: KiteConnect):
    global _instruments_cache, _instruments_loaded
    if _instruments_loaded:
        return
    instruments = kite.instruments("NSE")
    for inst in instruments:
        _instruments_cache[inst["tradingsymbol"]] = {
            "instrument_token": inst["instrument_token"],
            "name": inst["name"],
            "exchange": inst["exchange"],
        }
    _instruments_loaded = True


def get_instrument_token(symbol: str) -> Tuple[int, str]:
    """Returns (instrument_token, company_name) for the given NSE symbol."""
    kite = get_kite_client()
    load_instruments(kite)

    symbol = symbol.upper().strip().replace(".NS", "").replace(".BO", "")
    if symbol not in _instruments_cache:
        raise ValueError(f"Symbol '{symbol}' not found on NSE. Try the exact trading symbol (e.g., RELIANCE, INFY, TCS).")

    info = _instruments_cache[symbol]
    return info["instrument_token"], info["name"]


def fetch_historical(
    instrument_token: int,
    interval: str,
    days_back: int,
) -> List[Dict]:
    """Fetch OHLCV historical data for given interval and lookback period."""
    kite = get_kite_client()
    to_date = datetime.now(IST)
    from_date = to_date - timedelta(days=days_back)

    # Kite has no monthly interval — fetch daily and resample
    if interval == "month":
        return _fetch_monthly(kite, instrument_token, from_date, to_date)

    data = kite.historical_data(
        instrument_token=instrument_token,
        from_date=from_date.strftime("%Y-%m-%d %H:%M:%S"),
        to_date=to_date.strftime("%Y-%m-%d %H:%M:%S"),
        interval=interval,
    )
    return data


def _fetch_monthly(kite, instrument_token: int, from_date, to_date) -> List[Dict]:
    import pandas as pd
    daily = kite.historical_data(
        instrument_token=instrument_token,
        from_date=from_date.strftime("%Y-%m-%d %H:%M:%S"),
        to_date=to_date.strftime("%Y-%m-%d %H:%M:%S"),
        interval="day",
    )
    if not daily:
        return []
    df = pd.DataFrame(daily)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    monthly = df.resample("ME").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna().reset_index()
    return monthly.to_dict(orient="records")


def fetch_ltp(symbol: str) -> float:
    """Fetch the latest traded price for a symbol."""
    kite = get_kite_client()
    quote = kite.ltp([f"NSE:{symbol}"])
    return quote[f"NSE:{symbol}"]["last_price"]


def ohlcv_to_candles(data: List[Dict]) -> List[Dict]:
    """Convert Kite historical data to frontend-ready candle format."""
    candles = []
    for row in data:
        date = row["date"]
        if hasattr(date, "date"):
            date_str = date.strftime("%Y-%m-%d")
        else:
            date_str = str(date)[:10]
        candles.append({
            "date": date_str,
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": int(row["volume"]),
        })
    return candles
