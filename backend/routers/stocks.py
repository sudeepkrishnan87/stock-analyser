from fastapi import APIRouter, HTTPException, Query
from schemas import StockAnalysisResponse
from config import settings
from services import kite_service, nse_service, candlestick_service, elliott_wave_service, technical_service, claude_service

router = APIRouter()


@router.get("/{symbol}", response_model=StockAnalysisResponse)
def analyze_stock(symbol: str, exchange: str = Query(default="NSE")):
    """
    Full analysis for an Indian stock symbol.
    - Fetches daily / weekly / monthly OHLCV from Kite
    - Runs candlestick pattern detection
    - Detects Elliott Waves + Fibonacci levels
    - Computes RSI, MACD, Bollinger Bands, SMAs
    - Fetches FII/DII data from NSE India
    - Fetches quarterly results via yfinance
    - Generates AI analysis via Claude
    """
    if not settings.is_authenticated():
        raise HTTPException(
            status_code=401,
            detail="Kite access token not set. Please configure it via the Token Setup page.",
        )

    symbol = symbol.upper().strip()

    # ── 1. Instrument lookup ──────────────────────────────────────────────────
    try:
        instrument_token, company_name = kite_service.get_instrument_token(symbol)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Instrument lookup failed: {e}")

    # ── 2. Fetch OHLCV for daily / weekly / monthly ───────────────────────────
    try:
        daily_raw = kite_service.fetch_historical(instrument_token, "day", days_back=365)
        weekly_raw = kite_service.fetch_historical(instrument_token, "week", days_back=365 * 3)
        monthly_raw = kite_service.fetch_historical(instrument_token, "month", days_back=365 * 5)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Kite API error while fetching data: {e}")

    if not daily_raw:
        raise HTTPException(status_code=404, detail=f"No price data found for {symbol}.")

    daily_candles = kite_service.ohlcv_to_candles(daily_raw)
    weekly_candles = kite_service.ohlcv_to_candles(weekly_raw)
    monthly_candles = kite_service.ohlcv_to_candles(monthly_raw)

    current_price = daily_candles[-1]["close"]

    # ── 3. Build DataFrame for analysis ──────────────────────────────────────
    df_daily = technical_service.build_dataframe(daily_candles)

    # ── 4. Technical Indicators ───────────────────────────────────────────────
    indicators = technical_service.compute_indicators(df_daily)

    # ── 5. Candlestick Patterns ───────────────────────────────────────────────
    patterns = candlestick_service.detect_candlestick_patterns(df_daily, lookback=30)

    # ── 6. Elliott Waves + Fibonacci ─────────────────────────────────────────
    waves, fib_levels = elliott_wave_service.detect_elliott_waves(df_daily)

    # ── 7. FII / DII from NSE India ───────────────────────────────────────────
    fii_dii_data = nse_service.fetch_fii_dii_data(days=30)

    # ── 8. Quarterly Results from yfinance ───────────────────────────────────
    quarterly_results = nse_service.fetch_quarterly_results(symbol)

    # ── 9. AI Analysis via Claude ─────────────────────────────────────────────
    ai_result = claude_service.generate_ai_analysis(
        symbol=symbol,
        current_price=current_price,
        technical_indicators=indicators,
        candlestick_patterns=patterns,
        elliott_waves=waves,
        fibonacci_levels=fib_levels,
        fii_dii_data=fii_dii_data,
        quarterly_results=quarterly_results,
    )

    return StockAnalysisResponse(
        symbol=symbol,
        company_name=company_name,
        current_price=current_price,
        daily_candles=daily_candles,
        weekly_candles=weekly_candles,
        monthly_candles=monthly_candles,
        candlestick_patterns=[{
            "date": p["date"], "pattern": p["pattern"],
            "signal": p["signal"], "description": p["description"],
        } for p in patterns],
        elliott_waves=[{
            "wave_number": w["wave_number"],
            "start_date": w["start_date"], "end_date": w["end_date"],
            "start_price": w["start_price"], "end_price": w["end_price"],
            "wave_type": w["wave_type"],
        } for w in waves],
        fibonacci_levels=[{
            "level": f["level"], "price": f["price"], "label": f["label"],
        } for f in fib_levels],
        technical_indicators=indicators,
        fii_dii_data=[{
            "date": d["date"],
            "fii_buy": d["fii_buy"], "fii_sell": d["fii_sell"], "fii_net": d["fii_net"],
            "dii_buy": d["dii_buy"], "dii_sell": d["dii_sell"], "dii_net": d["dii_net"],
        } for d in fii_dii_data],
        quarterly_results=[{
            "quarter": q["quarter"],
            "revenue": q.get("revenue"),
            "net_profit": q.get("net_profit"),
            "eps": q.get("eps"),
        } for q in quarterly_results],
        ai_analysis=ai_result,
    )


@router.get("/search/{query}")
def search_symbols(query: str):
    """Quick symbol search — returns matching NSE tradingsymbols."""
    from services.kite_service import _instruments_cache, _instruments_loaded, get_kite_client, load_instruments
    if not settings.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated.")
    try:
        kite = get_kite_client()
        load_instruments(kite)
        q = query.upper()
        matches = [
            {"symbol": sym, "name": info["name"]}
            for sym, info in _instruments_cache.items()
            if q in sym or q in info["name"].upper()
        ]
        return {"results": matches[:20]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
