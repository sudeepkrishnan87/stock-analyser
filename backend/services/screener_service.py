"""
Multi-stock screener: runs all strategies on a watchlist and ranks results.

Strategies applied per stock:
  1. Volume spike  — volume_ratio >= 1.5x
  2. RSI zone      — 40-65 (sweet spot, not overbought)
  3. Bollinger Band — price approaching/touching lower band (buy zone)
                      or price above middle band with momentum
  4. Candlestick   — bullish reversal patterns in last 3 candles
  5. Trendline     — breakout / breakdown detection
  6. Elliott Wave  — detect Wave 3 / Wave 5 start (most profitable)
  7. Fundamentals  — P/E, EBITDA score >= 50
  8. MACD          — bullish crossover (MACD > signal)
  9. SMA trend     — price above SMA20 and SMA50

Each stock gets a composite SIGNAL_SCORE (0-100).
Stocks scoring >= 60 are flagged as actionable BUY candidates.
"""

import logging
from typing import List, Dict, Optional, Any

import pandas as pd

from services import (
    technical_service,
    candlestick_service,
    elliott_wave_service,
    trendline_service,
    fundamental_service,
)

logger = logging.getLogger(__name__)

BULLISH_CANDLES = {
    "Hammer", "Morning Star", "Dragonfly Doji",
    "Three White Soldiers", "Piercing Line", "Inverted Hammer",
    "Engulfing",
}

BEARISH_CANDLES = {
    "Shooting Star", "Evening Star", "Gravestone Doji",
    "Three Black Crows", "Dark Cloud Cover", "Engulfing",
}


def _volume_score(indicators: Dict) -> int:
    vr = indicators.get("volume_ratio", 0) or 0
    if vr >= 3.0: return 15
    if vr >= 2.0: return 12
    if vr >= 1.5: return 8
    if vr >= 1.2: return 4
    return 0


def _rsi_score(indicators: Dict) -> int:
    rsi = indicators.get("rsi")
    if rsi is None:
        return 0
    # Sweet spot: 45-65 (trending but not overbought)
    if 45 <= rsi <= 65: return 15
    if 40 <= rsi < 45:  return 10
    if 65 < rsi <= 70:  return 8
    if 35 <= rsi < 40:  return 5
    return 0   # <35 (too weak) or >70 (overbought)


def _rsi_score_short(indicators: Dict) -> int:
    rsi = indicators.get("rsi")
    if rsi is None:
        return 0
    # Sweet spot: 35-55 (already trending down, not yet oversold-bounce risk)
    if 35 <= rsi <= 55: return 15
    if 55 < rsi <= 60:  return 10
    if 30 <= rsi < 35:  return 8
    if 60 < rsi <= 70:  return 5
    return 0   # <30 (oversold, bounce risk) or >70 (still strong bullish momentum)


def _bollinger_score(df: pd.DataFrame, indicators: Dict) -> int:
    bb_lower = indicators.get("bb_lower")
    bb_middle = indicators.get("bb_middle")
    bb_upper = indicators.get("bb_upper")
    if not all([bb_lower, bb_middle, bb_upper]):
        return 0
    close = float(df["close"].iloc[-1])
    # Price near lower band = potential buy zone
    band_width = bb_upper - bb_lower
    if band_width == 0:
        return 0
    position = (close - bb_lower) / band_width  # 0=at lower, 1=at upper
    if position <= 0.2:   return 15   # Near lower band — oversold, mean reversion
    if position <= 0.35:  return 10
    if 0.5 <= position <= 0.7: return 8  # Above middle — bullish momentum
    return 3


def _bollinger_score_short(df: pd.DataFrame, indicators: Dict) -> int:
    bb_lower = indicators.get("bb_lower")
    bb_middle = indicators.get("bb_middle")
    bb_upper = indicators.get("bb_upper")
    if not all([bb_lower, bb_middle, bb_upper]):
        return 0
    close = float(df["close"].iloc[-1])
    band_width = bb_upper - bb_lower
    if band_width == 0:
        return 0
    position = (close - bb_lower) / band_width  # 0=at lower, 1=at upper
    if position >= 0.8:        return 15   # Near upper band — overbought, mean reversion down
    if position >= 0.65:       return 10
    if 0.3 <= position <= 0.5: return 8    # Below middle — bearish momentum
    return 3


def _candlestick_score(patterns: List[Dict]) -> int:
    if not patterns:
        return 0
    # Check last 3 candles only
    recent = [p for p in patterns[:6] if p.get("signal") == "bullish"]
    if not recent:
        return 0
    score = 0
    for p in recent[:2]:
        if p["pattern"] in BULLISH_CANDLES:
            score += 10
        else:
            score += 5
    return min(score, 15)


def _candlestick_score_short(patterns: List[Dict]) -> int:
    if not patterns:
        return 0
    recent = [p for p in patterns[:6] if p.get("signal") == "bearish"]
    if not recent:
        return 0
    score = 0
    for p in recent[:2]:
        if p["pattern"] in BEARISH_CANDLES:
            score += 10
        else:
            score += 5
    return min(score, 15)


def _macd_score(indicators: Dict) -> int:
    macd = indicators.get("macd")
    signal = indicators.get("macd_signal")
    hist = indicators.get("macd_histogram")
    if macd is None or signal is None:
        return 0
    if macd > signal and (hist or 0) > 0:
        return 10   # Bullish crossover with positive histogram
    if macd > signal:
        return 6
    return 0


def _macd_score_short(indicators: Dict) -> int:
    macd = indicators.get("macd")
    signal = indicators.get("macd_signal")
    hist = indicators.get("macd_histogram")
    if macd is None or signal is None:
        return 0
    if macd < signal and (hist or 0) < 0:
        return 10   # Bearish crossover with negative histogram
    if macd < signal:
        return 6
    return 0


def _sma_trend_score(df: pd.DataFrame, indicators: Dict) -> int:
    close = float(df["close"].iloc[-1])
    sma20 = indicators.get("sma_20")
    sma50 = indicators.get("sma_50")
    sma200 = indicators.get("sma_200")
    score = 0
    if sma20 and close > sma20: score += 4
    if sma50 and close > sma50: score += 4
    if sma200 and close > sma200: score += 4
    # Golden cross: SMA50 > SMA200
    if sma50 and sma200 and sma50 > sma200: score += 3
    return min(score, 15)


def _sma_trend_score_short(df: pd.DataFrame, indicators: Dict) -> int:
    close = float(df["close"].iloc[-1])
    sma20 = indicators.get("sma_20")
    sma50 = indicators.get("sma_50")
    sma200 = indicators.get("sma_200")
    score = 0
    if sma20 and close < sma20: score += 4
    if sma50 and close < sma50: score += 4
    if sma200 and close < sma200: score += 4
    # Death cross: SMA50 < SMA200
    if sma50 and sma200 and sma50 < sma200: score += 3
    return min(score, 15)


def _elliott_score(waves: List[Dict]) -> int:
    if not waves:
        return 0
    last_wave = waves[-1]
    wave_num = last_wave.get("wave_number", "")
    wave_type = last_wave.get("wave_type", "")
    # Wave 2 end = Wave 3 starting (most powerful move)
    if wave_num == "2" and wave_type == "motive":
        return 15
    # Wave 4 end = Wave 5 starting
    if wave_num == "4":
        return 12
    # Wave C end = new motive cycle starting
    if wave_num == "C" and wave_type == "corrective":
        return 12
    # Currently in Wave 3 (ride the strongest wave)
    if wave_num == "3":
        return 10
    return 3


def _elliott_score_short(waves: List[Dict]) -> int:
    """
    Mirrors _elliott_score() for bearish setups. Wave labeling itself is
    direction-agnostic (elliott_wave_service._label_waves just numbers the
    last 5/3 pivots) — so this checks the actual price direction of the
    relevant legs before scoring, rather than trusting the wave number alone.
    """
    if len(waves) < 2:
        return 0
    last = waves[-1]
    wave_num = last.get("wave_number", "")
    wave_type = last.get("wave_type", "")
    last_down = last.get("end_price", 0) < last.get("start_price", 0)

    # Wave "2" just completed as an UP bounce after a down wave "1" —
    # positions for wave 3 down, the strongest leg of a bearish impulse.
    if wave_num == "2" and wave_type == "motive" and not last_down:
        prev = waves[-2]
        prev_down = prev.get("end_price", 0) < prev.get("start_price", 0)
        if prev_down:
            return 15

    # Wave "4" just completed as a bounce after waves 1-3 down — positions
    # for wave 5 down.
    if wave_num == "4" and not last_down:
        return 12

    # Wave "C" just completed DOWN — corrective cycle finished bearish.
    if wave_num == "C" and wave_type == "corrective" and last_down:
        return 12

    # Currently inside wave "3" and it's moving down — ride the strongest leg.
    if wave_num == "3" and last_down:
        return 10

    # Any other clearly-down last leg gets a small credit.
    if last_down:
        return 3
    return 0


def _trendline_score(breakout_signal: Optional[Dict]) -> int:
    if not breakout_signal:
        return 0
    if breakout_signal.get("signal_type") == "BREAKOUT":
        base = 15
        if breakout_signal.get("volume_confirmed"):
            return base
        return base - 5
    return 0   # Breakdown = bearish, no score for BUY screen


def _trendline_score_short(breakout_signal: Optional[Dict]) -> int:
    if not breakout_signal:
        return 0
    if breakout_signal.get("signal_type") == "BREAKDOWN":
        base = 15
        if breakout_signal.get("volume_confirmed"):
            return base
        return base - 5
    return 0   # Breakout = bullish, no score for SHORT screen


def _fundamental_score_contribution(fundamentals: Optional[Dict]) -> int:
    if not fundamentals:
        return 5   # Unknown = neutral small score
    fs = fundamentals.get("fundamental_score", 0)
    if fs >= 75: return 15
    if fs >= 60: return 12
    if fs >= 50: return 8
    if fs >= 35: return 4
    return 0


def scan_symbol(
    symbol: str,
    df_daily: pd.DataFrame,
    include_fundamentals: bool = True,
) -> Dict:
    """
    Run all strategies on a single symbol's DataFrame.
    Returns a comprehensive scan result dict.
    """
    result: Dict[str, Any] = {"symbol": symbol, "signal": "NEUTRAL", "signal_score": 0}

    if len(df_daily) < 30:
        result["error"] = "Insufficient data"
        return result

    current_price = float(df_daily["close"].iloc[-1])
    result["current_price"] = round(current_price, 2)

    # ── Indicators ───────────────────────────────────────────────────────────
    try:
        indicators = technical_service.compute_indicators(df_daily)
    except Exception as e:
        indicators = {}
        logger.warning(f"{symbol} indicators failed: {e}")
    result["indicators"] = indicators

    # ── Candlestick patterns ─────────────────────────────────────────────────
    try:
        patterns = candlestick_service.detect_candlestick_patterns(df_daily, lookback=5)
    except Exception as e:
        patterns = []
        logger.warning(f"{symbol} candlestick failed: {e}")
    result["recent_patterns"] = patterns[:5]

    # ── Elliott Waves ────────────────────────────────────────────────────────
    try:
        waves, fib_levels = elliott_wave_service.detect_elliott_waves(df_daily)
    except Exception as e:
        waves, fib_levels = [], []
        logger.warning(f"{symbol} elliott failed: {e}")
    result["waves"] = waves
    result["fibonacci_levels"] = fib_levels

    # ── Trendline breakout ───────────────────────────────────────────────────
    try:
        rsi = indicators.get("rsi")
        breakout_signal = trendline_service.detect_breakout_breakdown(df_daily, rsi=rsi)
        trendlines = trendline_service.detect_trendlines(df_daily)
        horizontal = trendline_service.detect_horizontal_levels(df_daily)
    except Exception as e:
        breakout_signal = None
        trendlines = {}
        horizontal = {}
        logger.warning(f"{symbol} trendline failed: {e}")
    result["breakout_signal"] = breakout_signal
    result["trendlines"] = trendlines
    result["horizontal_levels"] = horizontal

    # ── Fundamentals (optional — slow, uses yfinance) ────────────────────────
    fundamentals = None
    if include_fundamentals:
        try:
            fundamentals = fundamental_service.fetch_fundamentals(symbol)
        except Exception as e:
            logger.warning(f"{symbol} fundamentals failed: {e}")
    result["fundamentals"] = fundamentals

    # ── Composite score ──────────────────────────────────────────────────────
    scores = {
        "volume":       _volume_score(indicators),
        "rsi":          _rsi_score(indicators),
        "bollinger":    _bollinger_score(df_daily, indicators),
        "candlestick":  _candlestick_score(patterns),
        "macd":         _macd_score(indicators),
        "sma_trend":    _sma_trend_score(df_daily, indicators),
        "elliott_wave": _elliott_score(waves),
        "trendline":    _trendline_score(breakout_signal),
        "fundamental":  _fundamental_score_contribution(fundamentals),
    }
    total_score = sum(scores.values())
    result["score_breakdown"] = scores
    result["signal_score"] = total_score

    # ── Signal classification ────────────────────────────────────────────────
    if total_score >= 75:
        signal = "STRONG BUY"
    elif total_score >= 60:
        signal = "BUY"
    elif total_score >= 45:
        signal = "WATCH"
    else:
        signal = "NEUTRAL"

    result["signal"] = signal

    # ── Suggested trade parameters ───────────────────────────────────────────
    if signal in ("BUY", "STRONG BUY"):
        rsi_val = indicators.get("rsi", 50)
        bb_lower = indicators.get("bb_lower", current_price * 0.97)

        # SL: below recent support or 3% from entry
        sl_candidates = [current_price * 0.97]
        if horizontal.get("support_levels"):
            nearest_sup = horizontal["support_levels"][0]["price"]
            if nearest_sup < current_price:
                sl_candidates.append(nearest_sup * 0.995)
        stop_loss = round(max(sl_candidates), 2)

        # Target: nearest resistance or 8% from entry
        target_candidates = [current_price * 1.08]
        if horizontal.get("resistance_levels"):
            nearest_res = horizontal["resistance_levels"][0]["price"]
            if nearest_res > current_price:
                target_candidates.append(nearest_res * 0.998)
        target = round(min(target_candidates), 2)

        risk = current_price - stop_loss
        reward = target - current_price
        rr = round(reward / risk, 2) if risk > 0 else 0

        # Only recommend if R:R >= 1.5
        if rr >= 1.5:
            result["trade_suggestion"] = {
                "entry": round(current_price, 2),
                "stop_loss": stop_loss,
                "target": target,
                "rr_ratio": rr,
                "trade_type": "INTRADAY" if rsi_val > 68 else "SWING",
                "risk_reward": f"1:{rr}",
            }

    # ── Short-side composite score (same indicators/patterns/waves/breakout —
    # no extra data fetch, just scored from the bearish angle) ───────────────
    short_scores = {
        "volume":       _volume_score(indicators),   # a volume spike matters either direction
        "rsi":          _rsi_score_short(indicators),
        "bollinger":    _bollinger_score_short(df_daily, indicators),
        "candlestick":  _candlestick_score_short(patterns),
        "macd":         _macd_score_short(indicators),
        "sma_trend":    _sma_trend_score_short(df_daily, indicators),
        "elliott_wave": _elliott_score_short(waves),
        "trendline":    _trendline_score_short(breakout_signal),
        "fundamental":  _fundamental_score_contribution(fundamentals),
    }
    short_total = sum(short_scores.values())
    result["short_score_breakdown"] = short_scores
    result["short_signal_score"] = short_total

    if short_total >= 75:
        short_signal = "STRONG SELL"
    elif short_total >= 60:
        short_signal = "SELL"
    elif short_total >= 45:
        short_signal = "WATCH"
    else:
        short_signal = "NEUTRAL"

    result["short_signal"] = short_signal

    # ── Suggested short-trade parameters ─────────────────────────────────────
    # Shorting cash equity in India is intraday-only for retail (MIS, must be
    # squared off same day — see trading_service.enter_trade's SHORT guard),
    # unlike the LONG side which can be SWING or INTRADAY.
    if short_signal in ("SELL", "STRONG SELL"):
        # SL: above recent resistance or 3% above entry — whichever is tighter
        sl_candidates = [current_price * 1.03]
        if horizontal.get("resistance_levels"):
            nearest_res = horizontal["resistance_levels"][0]["price"]
            if nearest_res > current_price:
                sl_candidates.append(nearest_res * 1.005)
        short_stop_loss = round(min(sl_candidates), 2)

        # Target: nearest support or 8% below entry — whichever is nearer/more achievable
        target_candidates = [current_price * 0.92]
        if horizontal.get("support_levels"):
            nearest_sup = horizontal["support_levels"][0]["price"]
            if nearest_sup < current_price:
                target_candidates.append(nearest_sup * 1.002)
        short_target = round(max(target_candidates), 2)

        short_risk = short_stop_loss - current_price
        short_reward = current_price - short_target
        short_rr = round(short_reward / short_risk, 2) if short_risk > 0 else 0

        if short_rr >= 1.5:
            result["short_trade_suggestion"] = {
                "entry": round(current_price, 2),
                "stop_loss": short_stop_loss,
                "target": short_target,
                "rr_ratio": short_rr,
                "trade_type": "INTRADAY",
                "risk_reward": f"1:{short_rr}",
            }

    return result


def scan_watchlist(
    symbols: List[str],
    broker,
    include_fundamentals: bool = False,
    min_score: int = 45,
) -> List[Dict]:
    """
    Scan all symbols in the watchlist. Fetches data via broker.
    Returns results sorted by signal_score descending.

    include_fundamentals=False by default for speed (yfinance adds ~2s/stock).
    """
    results = []

    for symbol in symbols:
        try:
            token, _ = broker.get_instrument_token(symbol)
            raw = broker.fetch_historical(token, "day", days_back=365)
            candles = broker.ohlcv_to_candles(raw)
            if not candles:
                continue
            df = technical_service.build_dataframe(candles)
            scan_result = scan_symbol(symbol, df, include_fundamentals=include_fundamentals)
            if scan_result.get("signal_score", 0) >= min_score:
                results.append(scan_result)
        except Exception as e:
            logger.warning(f"Scan failed for {symbol}: {e}")

    return sorted(results, key=lambda x: -x.get("signal_score", 0))


def scan_intraday(
    symbols: List[str],
    broker,
    interval: str = "15minute",
    days_back: int = 30,
) -> List[Dict]:
    """
    Intraday scan using 15-minute candles.
    Focuses on momentum and trendline breakouts for same-day trades.
    """
    results = []

    for symbol in symbols:
        try:
            token, _ = broker.get_instrument_token(symbol)
            raw = broker.fetch_historical(token, interval, days_back=days_back)
            candles = broker.ohlcv_to_candles(raw)
            if not candles:
                continue
            df = technical_service.build_dataframe(candles)
            scan_result = scan_symbol(symbol, df, include_fundamentals=False)
            scan_result["scan_timeframe"] = interval
            if scan_result.get("signal_score", 0) >= 50:
                results.append(scan_result)
        except Exception as e:
            logger.warning(f"Intraday scan failed for {symbol}: {e}")

    return sorted(results, key=lambda x: -x.get("signal_score", 0))
