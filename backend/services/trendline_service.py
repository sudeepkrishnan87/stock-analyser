"""
Trendline breakout/breakdown detection.

Approach:
  1. Find pivot highs (resistance) and pivot lows (support) using rolling windows.
  2. Fit a linear trendline through the last N pivot highs and N pivot lows.
  3. Determine where the trendline sits today.
  4. Detect breakout  → current close > resistance trendline AND volume confirmation.
  5. Detect breakdown → current close < support trendline AND volume confirmation.

Breakout/breakdown signals are stronger when:
  - Volume on breakout candle is ≥ 1.5× 20-day average (volume confirmation).
  - The break is ≥ 0.5% above/below the trendline (filter false breaks).
  - RSI is not in extreme overbought/oversold territory against the signal direction.
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple
from scipy.signal import argrelextrema


def _find_pivot_highs(series: np.ndarray, order: int = 5) -> List[int]:
    idx = argrelextrema(series, np.greater_equal, order=order)[0]
    return list(idx)


def _find_pivot_lows(series: np.ndarray, order: int = 5) -> List[int]:
    idx = argrelextrema(series, np.less_equal, order=order)[0]
    return list(idx)


def _fit_trendline(x_indices: List[int], y_values: List[float]) -> Optional[Tuple[float, float]]:
    """Fit y = slope * x + intercept via least-squares. Returns (slope, intercept)."""
    if len(x_indices) < 2:
        return None
    x = np.array(x_indices, dtype=float)
    y = np.array(y_values, dtype=float)
    coeffs = np.polyfit(x, y, 1)
    return float(coeffs[0]), float(coeffs[1])


def _trendline_value(slope: float, intercept: float, x: int) -> float:
    return slope * x + intercept


def detect_trendlines(df: pd.DataFrame, pivot_order: int = 5, num_pivots: int = 4) -> Dict:
    """
    Detect support and resistance trendlines from OHLCV DataFrame.

    Returns:
    {
        "resistance": {"slope": float, "intercept": float, "current_value": float, "pivot_points": [...]},
        "support":    {"slope": float, "intercept": float, "current_value": float, "pivot_points": [...]},
    }
    """
    if len(df) < 30:
        return {}

    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    pivot_h_idx = _find_pivot_highs(highs, order=pivot_order)
    pivot_l_idx = _find_pivot_lows(lows, order=pivot_order)

    # Use the last `num_pivots` pivots
    recent_h = pivot_h_idx[-num_pivots:] if len(pivot_h_idx) >= num_pivots else pivot_h_idx
    recent_l = pivot_l_idx[-num_pivots:] if len(pivot_l_idx) >= num_pivots else pivot_l_idx

    result: Dict = {}

    # Resistance trendline (through pivot highs)
    if recent_h:
        h_vals = [highs[i] for i in recent_h]
        fit = _fit_trendline(recent_h, h_vals)
        if fit:
            slope, intercept = fit
            current_resistance = _trendline_value(slope, intercept, n - 1)
            result["resistance"] = {
                "slope": round(slope, 4),
                "intercept": round(intercept, 2),
                "current_value": round(current_resistance, 2),
                "pivot_points": [
                    {"index": int(i), "date": df.index[i].strftime("%Y-%m-%d"), "price": round(highs[i], 2)}
                    for i in recent_h
                ],
            }

    # Support trendline (through pivot lows)
    if recent_l:
        l_vals = [lows[i] for i in recent_l]
        fit = _fit_trendline(recent_l, l_vals)
        if fit:
            slope, intercept = fit
            current_support = _trendline_value(slope, intercept, n - 1)
            result["support"] = {
                "slope": round(slope, 4),
                "intercept": round(intercept, 2),
                "current_value": round(current_support, 2),
                "pivot_points": [
                    {"index": int(i), "date": df.index[i].strftime("%Y-%m-%d"), "price": round(lows[i], 2)}
                    for i in recent_l
                ],
            }

    return result


def detect_breakout_breakdown(df: pd.DataFrame, rsi: Optional[float] = None) -> Optional[Dict]:
    """
    Main entry: detect trendline breakout or breakdown on the latest candle.

    Returns dict with signal info or None if no actionable signal.
    """
    if len(df) < 30:
        return None

    trendlines = detect_trendlines(df)
    if not trendlines:
        return None

    current_close = float(df["close"].iloc[-1])
    current_vol = float(df["volume"].iloc[-1])
    avg_vol = float(df["volume"].rolling(20).mean().iloc[-1])
    volume_ratio = current_vol / avg_vol if avg_vol > 0 else 1.0
    volume_confirmed = volume_ratio >= 1.5

    # ── Breakout (close > resistance trendline) ───────────────────────────
    if "resistance" in trendlines:
        resistance = trendlines["resistance"]["current_value"]
        breakout_pct = ((current_close - resistance) / resistance) * 100
        # RSI should NOT be overbought (>80) on breakout — filter false signals
        rsi_ok = (rsi is None) or (rsi < 80)
        if breakout_pct >= 0.5 and volume_confirmed and rsi_ok:
            return {
                "signal_type": "BREAKOUT",
                "direction": "BULLISH",
                "trendline_value": resistance,
                "current_price": current_close,
                "breakout_pct": round(breakout_pct, 2),
                "volume_ratio": round(volume_ratio, 2),
                "volume_confirmed": True,
                "suggested_entry": round(current_close, 2),
                "suggested_sl": round(resistance * 0.98, 2),     # 2% below breakout level
                "suggested_target": round(current_close * 1.08, 2),  # 8% above breakout
                "rr_ratio": round((current_close * 1.08 - current_close) / (current_close - resistance * 0.98), 2),
                "message": (
                    f"TRENDLINE BREAKOUT: Price ₹{current_close:.2f} broke above "
                    f"resistance ₹{resistance:.2f} (+{breakout_pct:.2f}%) with "
                    f"{volume_ratio:.1f}x volume."
                ),
            }

    # ── Breakdown (close < support trendline) ────────────────────────────
    if "support" in trendlines:
        support = trendlines["support"]["current_value"]
        breakdown_pct = ((support - current_close) / support) * 100
        rsi_ok = (rsi is None) or (rsi > 20)
        if breakdown_pct >= 0.5 and volume_confirmed and rsi_ok:
            return {
                "signal_type": "BREAKDOWN",
                "direction": "BEARISH",
                "trendline_value": support,
                "current_price": current_close,
                "breakout_pct": round(breakdown_pct, 2),
                "volume_ratio": round(volume_ratio, 2),
                "volume_confirmed": True,
                "suggested_entry": round(current_close, 2),
                "suggested_sl": round(support * 1.02, 2),           # 2% above breakdown level
                "suggested_target": round(current_close * 0.92, 2),  # 8% below breakdown
                "rr_ratio": round((support * 1.02 - current_close) / (current_close - current_close * 0.92), 2),
                "message": (
                    f"TRENDLINE BREAKDOWN: Price ₹{current_close:.2f} broke below "
                    f"support ₹{support:.2f} (-{breakdown_pct:.2f}%) with "
                    f"{volume_ratio:.1f}x volume."
                ),
            }

    return None


def detect_horizontal_levels(df: pd.DataFrame, tolerance_pct: float = 0.5) -> Dict:
    """
    Detect horizontal support/resistance levels (price clusters).
    Clusters multiple touches within tolerance_pct into a single level.
    """
    if len(df) < 30:
        return {"resistance_levels": [], "support_levels": []}

    highs = df["high"].values
    lows = df["low"].values
    order = max(3, len(df) // 30)

    ph_idx = _find_pivot_highs(highs, order=order)
    pl_idx = _find_pivot_lows(lows, order=order)

    def cluster(prices: List[float]) -> List[Dict]:
        if not prices:
            return []
        prices_sorted = sorted(prices)
        clusters = [[prices_sorted[0]]]
        for p in prices_sorted[1:]:
            if abs(p - clusters[-1][-1]) / clusters[-1][-1] * 100 <= tolerance_pct:
                clusters[-1].append(p)
            else:
                clusters.append([p])
        result = []
        for c in clusters:
            if len(c) >= 2:  # Only levels with 2+ touches
                result.append({
                    "price": round(float(np.mean(c)), 2),
                    "touches": len(c),
                    "strength": "STRONG" if len(c) >= 3 else "MODERATE",
                })
        return sorted(result, key=lambda x: -x["touches"])

    resistance_prices = [highs[i] for i in ph_idx]
    support_prices = [lows[i] for i in pl_idx]

    return {
        "resistance_levels": cluster(resistance_prices)[:5],
        "support_levels": cluster(support_prices)[:5],
    }
