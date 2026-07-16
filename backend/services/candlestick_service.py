import pandas as pd
from typing import List, Dict

PATTERN_META = {
    "doji":               ("Doji",                 "neutral",  "Indecision candle — market at equilibrium"),
    "hammer":             ("Hammer",                "bullish",  "Potential bullish reversal from downtrend"),
    "shootingstar":       ("Shooting Star",         "bearish",  "Potential bearish reversal from uptrend"),
    "engulfing":          ("Engulfing",             None,       "Strong momentum reversal pattern"),
    "morningstar":        ("Morning Star",          "bullish",  "3-candle bullish reversal at the bottom"),
    "eveningstar":        ("Evening Star",          "bearish",  "3-candle bearish reversal at the top"),
    "harami":             ("Harami",                None,       "Inside bar — possible trend change"),
    "marubozu":           ("Marubozu",              None,       "Strong momentum candle — no shadows"),
    "dragonflydoji":      ("Dragonfly Doji",        "bullish",  "Bullish reversal signal"),
    "gravestonedoji":     ("Gravestone Doji",       "bearish",  "Bearish reversal signal"),
    "threewhitesoldiers": ("Three White Soldiers",  "bullish",  "Strong 3-candle bullish reversal"),
    "threeblackcrows":    ("Three Black Crows",     "bearish",  "Strong 3-candle bearish reversal"),
    "piercingline":       ("Piercing Line",         "bullish",  "Bullish 2-candle reversal at bottom"),
    "darkcloudcover":     ("Dark Cloud Cover",      "bearish",  "Bearish 2-candle reversal at top"),
    "invertedhammer":     ("Inverted Hammer",       "bullish",  "Potential reversal — needs confirmation"),
}


def _body(o, c): return abs(c - o)
def _upper_shadow(o, h, c): return h - max(o, c)
def _lower_shadow(o, l, c): return min(o, c) - l
def _range(h, l): return h - l if h != l else 1e-9
def _is_bullish(o, c): return c > o
def _is_bearish(o, c): return c < o


def _detect_row(pattern_key: str, df: pd.DataFrame) -> List[pd.Timestamp]:
    """Return index timestamps where the pattern fires."""
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    idx = df.index
    hits = []
    n = len(df)

    for i in range(n):
        body   = _body(o[i], c[i])
        hi_rng = _range(h[i], l[i])
        up_sh  = _upper_shadow(o[i], h[i], c[i])
        lo_sh  = _lower_shadow(o[i], l[i], c[i])

        if pattern_key == "doji":
            # Body ≤ 10 % of range
            if body <= 0.1 * hi_rng:
                hits.append(idx[i])

        elif pattern_key == "dragonflydoji":
            # Near-zero body, tiny upper shadow, long lower shadow
            if body <= 0.1 * hi_rng and up_sh <= 0.1 * hi_rng and lo_sh >= 0.6 * hi_rng:
                hits.append(idx[i])

        elif pattern_key == "gravestonedoji":
            # Near-zero body, long upper shadow, tiny lower shadow
            if body <= 0.1 * hi_rng and lo_sh <= 0.1 * hi_rng and up_sh >= 0.6 * hi_rng:
                hits.append(idx[i])

        elif pattern_key == "hammer":
            # Bullish: small body at top, lower shadow ≥ 2× body, tiny upper shadow
            if body > 0 and _is_bullish(o[i], c[i]):
                if lo_sh >= 2 * body and up_sh <= 0.3 * body:
                    hits.append(idx[i])

        elif pattern_key == "invertedhammer":
            # Bullish: small body at bottom, upper shadow ≥ 2× body, tiny lower shadow
            if body > 0 and _is_bullish(o[i], c[i]):
                if up_sh >= 2 * body and lo_sh <= 0.3 * body:
                    hits.append(idx[i])

        elif pattern_key == "shootingstar":
            # Bearish: small body at bottom, upper shadow ≥ 2× body, tiny lower shadow
            if body > 0 and _is_bearish(o[i], c[i]):
                if up_sh >= 2 * body and lo_sh <= 0.3 * body:
                    hits.append(idx[i])

        elif pattern_key == "marubozu":
            # Tiny shadows (≤ 5 % of range each) — strong momentum candle
            if body >= 0.85 * hi_rng and up_sh <= 0.05 * hi_rng and lo_sh <= 0.05 * hi_rng:
                hits.append(idx[i])

        elif pattern_key == "engulfing" and i >= 1:
            prev_body = _body(o[i-1], c[i-1])
            # Bullish engulfing
            if _is_bearish(o[i-1], c[i-1]) and _is_bullish(o[i], c[i]):
                if body > prev_body and o[i] <= c[i-1] and c[i] >= o[i-1]:
                    hits.append(idx[i])
            # Bearish engulfing
            elif _is_bullish(o[i-1], c[i-1]) and _is_bearish(o[i], c[i]):
                if body > prev_body and o[i] >= c[i-1] and c[i] <= o[i-1]:
                    hits.append(idx[i])

        elif pattern_key == "harami" and i >= 1:
            prev_body = _body(o[i-1], c[i-1])
            # Inside candle
            if body < prev_body:
                inner_high = max(o[i], c[i])
                inner_low  = min(o[i], c[i])
                outer_high = max(o[i-1], c[i-1])
                outer_low  = min(o[i-1], c[i-1])
                if inner_high <= outer_high and inner_low >= outer_low:
                    hits.append(idx[i])

        elif pattern_key == "piercingline" and i >= 1:
            # Prior bearish, current bullish opening below prior low, closing > midpoint of prior body
            if _is_bearish(o[i-1], c[i-1]) and _is_bullish(o[i], c[i]):
                prior_mid = (o[i-1] + c[i-1]) / 2
                if o[i] < c[i-1] and c[i] > prior_mid and c[i] < o[i-1]:
                    hits.append(idx[i])

        elif pattern_key == "darkcloudcover" and i >= 1:
            # Prior bullish, current bearish opening above prior high, closing < midpoint of prior body
            if _is_bullish(o[i-1], c[i-1]) and _is_bearish(o[i], c[i]):
                prior_mid = (o[i-1] + c[i-1]) / 2
                if o[i] > c[i-1] and c[i] < prior_mid and c[i] > o[i-1]:
                    hits.append(idx[i])

        elif pattern_key == "morningstar" and i >= 2:
            # C1 bearish large, C2 small body gap down, C3 bullish closes > C1 midpoint
            c1_body = _body(o[i-2], c[i-2])
            c2_body = _body(o[i-1], c[i-1])
            c3_body = _body(o[i],   c[i])
            c1_mid  = (o[i-2] + c[i-2]) / 2
            if (
                _is_bearish(o[i-2], c[i-2]) and c1_body > 0
                and c2_body < 0.3 * c1_body
                and _is_bullish(o[i], c[i]) and c[i] > c1_mid
            ):
                hits.append(idx[i])

        elif pattern_key == "eveningstar" and i >= 2:
            # C1 bullish large, C2 small body gap up, C3 bearish closes < C1 midpoint
            c1_body = _body(o[i-2], c[i-2])
            c2_body = _body(o[i-1], c[i-1])
            c1_mid  = (o[i-2] + c[i-2]) / 2
            if (
                _is_bullish(o[i-2], c[i-2]) and c1_body > 0
                and c2_body < 0.3 * c1_body
                and _is_bearish(o[i], c[i]) and c[i] < c1_mid
            ):
                hits.append(idx[i])

        elif pattern_key == "threewhitesoldiers" and i >= 2:
            # 3 consecutive bullish candles, each closing higher
            if (
                _is_bullish(o[i-2], c[i-2])
                and _is_bullish(o[i-1], c[i-1])
                and _is_bullish(o[i],   c[i])
                and c[i]   > c[i-1]
                and c[i-1] > c[i-2]
                and o[i]   > o[i-1] > o[i-2]
            ):
                hits.append(idx[i])

        elif pattern_key == "threeblackcrows" and i >= 2:
            # 3 consecutive bearish candles, each closing lower
            if (
                _is_bearish(o[i-2], c[i-2])
                and _is_bearish(o[i-1], c[i-1])
                and _is_bearish(o[i],   c[i])
                and c[i]   < c[i-1]
                and c[i-1] < c[i-2]
                and o[i]   < o[i-1] < o[i-2]
            ):
                hits.append(idx[i])

    return hits


def detect_candlestick_patterns(df: pd.DataFrame, lookback: int = 30) -> List[Dict]:
    if len(df) < 5:
        return []

    recent_df = df.tail(lookback + 10)
    detected  = []

    for pattern_key, (name, default_signal, desc) in PATTERN_META.items():
        try:
            hits = _detect_row(pattern_key, recent_df)
            # Only keep last `lookback` worth
            cutoff = df.index[-lookback] if len(df) > lookback else df.index[0]
            for ts in hits:
                if ts < cutoff:
                    continue

                if pattern_key == "engulfing":
                    signal = "bullish" if _is_bullish(
                        recent_df.at[ts, "open"], recent_df.at[ts, "close"]
                    ) else "bearish"
                elif pattern_key == "harami":
                    prev_ts = recent_df.index[recent_df.index.get_loc(ts) - 1]
                    signal = "bullish" if _is_bearish(
                        recent_df.at[prev_ts, "open"], recent_df.at[prev_ts, "close"]
                    ) else "bearish"
                elif pattern_key == "marubozu":
                    signal = "bullish" if _is_bullish(
                        recent_df.at[ts, "open"], recent_df.at[ts, "close"]
                    ) else "bearish"
                else:
                    signal = default_signal

                date_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
                detected.append({
                    "date":        date_str,
                    "pattern":     name,
                    "signal":      signal,
                    "description": desc,
                })
        except Exception:
            continue

    seen = set()
    unique = []
    for item in sorted(detected, key=lambda x: x["date"], reverse=True):
        key = (item["date"], item["pattern"])
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique[:20]
