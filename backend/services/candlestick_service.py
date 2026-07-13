import pandas as pd
import pandas_ta as ta
from typing import List, Dict

PATTERN_META = {
    "doji": ("Doji", "neutral", "Indecision candle — market at equilibrium"),
    "hammer": ("Hammer", "bullish", "Potential bullish reversal from downtrend"),
    "shootingstar": ("Shooting Star", "bearish", "Potential bearish reversal from uptrend"),
    "engulfing": ("Engulfing", None, "Strong momentum reversal pattern"),
    "morningstar": ("Morning Star", "bullish", "3-candle bullish reversal at the bottom"),
    "eveningstar": ("Evening Star", "bearish", "3-candle bearish reversal at the top"),
    "harami": ("Harami", None, "Inside bar — possible trend change"),
    "marubozu": ("Marubozu", None, "Strong momentum candle — no shadows"),
    "dragonflydoji": ("Dragonfly Doji", "bullish", "Bullish reversal signal"),
    "gravestonedoji": ("Gravestone Doji", "bearish", "Bearish reversal signal"),
    "threewhitesoldiers": ("Three White Soldiers", "bullish", "Strong 3-candle bullish reversal"),
    "threeblackcrows": ("Three Black Crows", "bearish", "Strong 3-candle bearish reversal"),
    "piercingline": ("Piercing Line", "bullish", "Bullish 2-candle reversal at bottom"),
    "darkcloudcover": ("Dark Cloud Cover", "bearish", "Bearish 2-candle reversal at top"),
    "invertedhammer": ("Inverted Hammer", "bullish", "Potential reversal — needs confirmation"),
}


def detect_candlestick_patterns(df: pd.DataFrame, lookback: int = 30) -> List[Dict]:
    """
    Detect candlestick patterns in the last `lookback` candles.
    Returns list of {date, pattern, signal, description}.
    """
    if len(df) < 5:
        return []

    detected = []
    recent_df = df.tail(lookback + 10)  # Extra buffer for multi-candle patterns

    for pattern_key, (name, default_signal, desc) in PATTERN_META.items():
        try:
            result = recent_df.ta.cdl_pattern(name=pattern_key)
            if result is None or result.empty:
                continue

            # result is a DataFrame; keep last `lookback` rows
            result = result.tail(lookback)

            for col in result.columns:
                series = result[col]
                non_zero = series[series != 0]
                for date_idx, value in non_zero.items():
                    signal = default_signal
                    if signal is None:
                        signal = "bullish" if float(value) > 0 else "bearish"

                    date_str = (
                        date_idx.strftime("%Y-%m-%d")
                        if hasattr(date_idx, "strftime")
                        else str(date_idx)[:10]
                    )
                    detected.append({
                        "date": date_str,
                        "pattern": name,
                        "signal": signal,
                        "description": desc,
                    })
        except Exception:
            continue

    # Sort by date descending, deduplicate same pattern on same date
    seen = set()
    unique = []
    for item in sorted(detected, key=lambda x: x["date"], reverse=True):
        key = (item["date"], item["pattern"])
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique[:20]  # Return latest 20 signals
