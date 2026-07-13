import numpy as np
import pandas as pd
from scipy.signal import argrelextrema
from typing import List, Dict, Tuple


def _apply_zigzag(extrema: List[Dict], min_move_pct: float) -> List[Dict]:
    """Filter extrema to only keep significant swings (> min_move_pct)."""
    if not extrema:
        return []

    filtered = [extrema[0]]
    for point in extrema[1:]:
        last = filtered[-1]
        if last["type"] == point["type"]:
            # Same type — keep more extreme value
            if point["type"] == "high" and point["price"] >= last["price"]:
                filtered[-1] = point
            elif point["type"] == "low" and point["price"] <= last["price"]:
                filtered[-1] = point
        else:
            # Alternating types — check move size
            move_pct = abs(point["price"] - last["price"]) / last["price"] * 100
            if move_pct >= min_move_pct:
                filtered.append(point)

    return filtered


def _find_pivots(df: pd.DataFrame) -> List[Dict]:
    """Identify significant price pivots using local extrema + zigzag filter."""
    close = df["close"].values
    n = len(close)

    if n < 20:
        return []

    order = max(3, n // 40)

    peak_idx = argrelextrema(close, np.greater_equal, order=order)[0]
    trough_idx = argrelextrema(close, np.less_equal, order=order)[0]

    extrema = []
    for i in peak_idx:
        extrema.append({"idx": int(i), "price": float(close[i]), "type": "high", "date": df.index[i]})
    for i in trough_idx:
        extrema.append({"idx": int(i), "price": float(close[i]), "type": "low", "date": df.index[i]})

    extrema.sort(key=lambda x: x["idx"])

    # Remove duplicate indices
    seen = set()
    unique = []
    for e in extrema:
        if e["idx"] not in seen:
            seen.add(e["idx"])
            unique.append(e)

    # ZigZag: filter moves smaller than 3% or ₹X, whichever is more conservative
    avg_price = float(np.mean(close))
    min_move_pct = max(2.5, (avg_price * 0.03 / avg_price) * 100)

    filtered = _apply_zigzag(unique, min_move_pct)
    return filtered


def _label_waves(pivots: List[Dict]) -> List[Dict]:
    """Label the last N pivots as Elliott Wave numbers."""
    if len(pivots) < 2:
        return []

    waves = []
    n = len(pivots)

    def fmt_date(d) -> str:
        return d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]

    if n >= 6:
        # Label last 5 moves as motive waves 1-5
        recent = pivots[-6:]
        labels = ["1", "2", "3", "4", "5"]
        wave_type = "motive"
    elif n >= 4:
        # Label last 3 moves as corrective ABC
        recent = pivots[-4:]
        labels = ["A", "B", "C"]
        wave_type = "corrective"
    else:
        recent = pivots
        labels = [str(i + 1) for i in range(n - 1)]
        wave_type = "motive"

    for i in range(min(len(labels), len(recent) - 1)):
        waves.append({
            "wave_number": labels[i],
            "start_date": fmt_date(recent[i]["date"]),
            "end_date": fmt_date(recent[i + 1]["date"]),
            "start_price": round(recent[i]["price"], 2),
            "end_price": round(recent[i + 1]["price"], 2),
            "wave_type": wave_type,
        })

    return waves


def _calculate_fibonacci(pivots: List[Dict]) -> List[Dict]:
    """Calculate Fibonacci retracement and extension levels from last swing."""
    if len(pivots) < 2:
        return []

    # Use last significant swing for levels
    p1 = pivots[-2]
    p2 = pivots[-1]

    swing_low = min(p1["price"], p2["price"])
    swing_high = max(p1["price"], p2["price"])
    swing_range = swing_high - swing_low
    direction = 1 if p2["price"] > p1["price"] else -1  # 1 = up, -1 = down

    levels = []
    ret_ratios = [(0.236, "23.6% Ret"), (0.382, "38.2% Ret"), (0.5, "50.0% Ret"),
                  (0.618, "61.8% Ret"), (0.786, "78.6% Ret")]
    ext_ratios = [(1.0, "100% Ext"), (1.272, "127.2% Ext"), (1.618, "161.8% Ext"),
                  (2.0, "200% Ext"), (2.618, "261.8% Ext")]

    # Retracements from p2
    for ratio, label in ret_ratios:
        price = p2["price"] - direction * swing_range * ratio
        levels.append({"level": ratio, "price": round(price, 2), "label": label})

    # Extensions beyond p2 (trend continuation targets)
    for ratio, label in ext_ratios:
        price = p1["price"] + direction * swing_range * ratio
        levels.append({"level": ratio, "price": round(price, 2), "label": label})

    return levels


def detect_elliott_waves(df: pd.DataFrame) -> Tuple[List[Dict], List[Dict]]:
    """
    Main entry point.
    Returns (waves, fibonacci_levels).
    """
    pivots = _find_pivots(df)

    if not pivots:
        return [], []

    waves = _label_waves(pivots)
    fib_levels = _calculate_fibonacci(pivots)

    return waves, fib_levels
