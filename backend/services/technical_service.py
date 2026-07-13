import pandas as pd
import pandas_ta as ta
from typing import List, Dict, Optional


def build_dataframe(candles: List[Dict]) -> pd.DataFrame:
    """Convert list of OHLCV dicts to a pandas DataFrame."""
    df = pd.DataFrame(candles)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    return df


def compute_indicators(df: pd.DataFrame) -> dict:
    """Compute RSI, MACD, Bollinger Bands, SMAs, volume ratio."""
    indicators = {}

    if len(df) < 20:
        return indicators

    try:
        # RSI(14)
        rsi_series = df.ta.rsi(length=14)
        if rsi_series is not None and not rsi_series.empty:
            val = rsi_series.dropna()
            if not val.empty:
                indicators["rsi"] = round(float(val.iloc[-1]), 2)
    except Exception:
        pass

    try:
        # MACD(12,26,9)
        macd_df = df.ta.macd(fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            last = macd_df.dropna().iloc[-1] if not macd_df.dropna().empty else None
            if last is not None:
                for col in macd_df.columns:
                    if col.startswith("MACD_"):
                        indicators["macd"] = round(float(last[col]), 4)
                    elif col.startswith("MACDs_"):
                        indicators["macd_signal"] = round(float(last[col]), 4)
                    elif col.startswith("MACDh_"):
                        indicators["macd_histogram"] = round(float(last[col]), 4)
    except Exception:
        pass

    try:
        # Bollinger Bands(20, 2)
        bb_df = df.ta.bbands(length=20, std=2)
        if bb_df is not None and not bb_df.empty:
            last = bb_df.dropna().iloc[-1] if not bb_df.dropna().empty else None
            if last is not None:
                for col in bb_df.columns:
                    if col.startswith("BBL_"):
                        indicators["bb_lower"] = round(float(last[col]), 2)
                    elif col.startswith("BBM_"):
                        indicators["bb_middle"] = round(float(last[col]), 2)
                    elif col.startswith("BBU_"):
                        indicators["bb_upper"] = round(float(last[col]), 2)
    except Exception:
        pass

    try:
        # Moving Averages
        for period, key in [(20, "sma_20"), (50, "sma_50"), (200, "sma_200")]:
            if len(df) >= period:
                sma = df.ta.sma(length=period)
                if sma is not None and not sma.dropna().empty:
                    indicators[key] = round(float(sma.dropna().iloc[-1]), 2)
    except Exception:
        pass

    try:
        # Volume ratio (current / 20-day avg)
        vol_avg = df["volume"].rolling(20).mean().iloc[-1]
        if vol_avg and vol_avg > 0:
            indicators["volume_ratio"] = round(float(df["volume"].iloc[-1]) / float(vol_avg), 2)
    except Exception:
        pass

    return indicators
