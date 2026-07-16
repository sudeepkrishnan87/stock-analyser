import pandas as pd
import ta
from typing import List, Dict


def build_dataframe(candles: List[Dict]) -> pd.DataFrame:
    df = pd.DataFrame(candles)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    return df


def compute_indicators(df: pd.DataFrame) -> dict:
    indicators = {}
    if len(df) < 20:
        return indicators

    try:
        rsi = ta.momentum.RSIIndicator(close=df["close"], window=14).rsi().dropna()
        if not rsi.empty:
            indicators["rsi"] = round(float(rsi.iloc[-1]), 2)
    except Exception:
        pass

    try:
        macd_obj = ta.trend.MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
        macd_val = macd_obj.macd().dropna()
        sig_val  = macd_obj.macd_signal().dropna()
        hist_val = macd_obj.macd_diff().dropna()
        if not macd_val.empty:
            indicators["macd"]           = round(float(macd_val.iloc[-1]), 4)
            indicators["macd_signal"]    = round(float(sig_val.iloc[-1]), 4)
            indicators["macd_histogram"] = round(float(hist_val.iloc[-1]), 4)
    except Exception:
        pass

    try:
        bb = ta.volatility.BollingerBands(close=df["close"], window=20, window_dev=2)
        indicators["bb_upper"]  = round(float(bb.bollinger_hband().dropna().iloc[-1]), 2)
        indicators["bb_middle"] = round(float(bb.bollinger_mavg().dropna().iloc[-1]), 2)
        indicators["bb_lower"]  = round(float(bb.bollinger_lband().dropna().iloc[-1]), 2)
    except Exception:
        pass

    try:
        for period, key in [(20, "sma_20"), (50, "sma_50"), (200, "sma_200")]:
            if len(df) >= period:
                sma = ta.trend.SMAIndicator(close=df["close"], window=period).sma_indicator().dropna()
                if not sma.empty:
                    indicators[key] = round(float(sma.iloc[-1]), 2)
    except Exception:
        pass

    try:
        vol_avg = df["volume"].rolling(20).mean().iloc[-1]
        if vol_avg and vol_avg > 0:
            indicators["volume_ratio"] = round(float(df["volume"].iloc[-1]) / float(vol_avg), 2)
    except Exception:
        pass

    return indicators
