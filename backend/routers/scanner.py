"""
Scanner endpoints:
  GET  /api/scanner/watchlist          — scan default watchlist (swing)
  GET  /api/scanner/intraday           — scan for intraday setups (15-min candles)
  GET  /api/scanner/symbol/{symbol}    — deep scan a single symbol
  POST /api/scanner/watchlist/custom   — scan a custom list of symbols
  POST /api/scanner/trigger/{type}     — manually trigger a scheduled scan job
  GET  /api/scanner/scheduler          — scheduler status
"""

from fastapi import APIRouter, HTTPException, Query, Body
from typing import List, Optional

from config import settings
from services import screener_service, scheduler_service, technical_service
from services import trendline_service, fundamental_service, elliott_wave_service, candlestick_service
from services import kite_service

router = APIRouter()


def _get_broker():
    if not settings.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated with any broker.")
    from brokers.zerodha import ZerodhaBroker
    return ZerodhaBroker()


@router.get("/watchlist")
def scan_watchlist(
    min_score: int = Query(default=55, ge=0, le=100),
    include_fundamentals: bool = Query(default=False),
    limit: int = Query(default=10, ge=1, le=30),
):
    """Swing scan on the default watchlist. Returns top picks sorted by signal score."""
    broker = _get_broker()
    try:
        results = screener_service.scan_watchlist(
            settings.DEFAULT_WATCHLIST,
            broker=broker,
            include_fundamentals=include_fundamentals,
            min_score=min_score,
        )
        return {
            "scan_type": "SWING",
            "symbols_scanned": len(settings.DEFAULT_WATCHLIST),
            "candidates_found": len(results),
            "results": results[:limit],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/intraday")
def scan_intraday(
    interval: str = Query(default="15minute", pattern="^(5minute|15minute|30minute|60minute)$"),
    limit: int = Query(default=10, ge=1, le=20),
):
    """Intraday momentum scan using sub-hourly candles."""
    broker = _get_broker()
    try:
        results = screener_service.scan_intraday(
            settings.DEFAULT_WATCHLIST[:20],
            broker=broker,
            interval=interval,
            days_back=30,
        )
        return {
            "scan_type": "INTRADAY",
            "interval": interval,
            "symbols_scanned": min(20, len(settings.DEFAULT_WATCHLIST)),
            "candidates_found": len(results),
            "results": results[:limit],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbol/{symbol}")
def scan_symbol(
    symbol: str,
    include_fundamentals: bool = Query(default=True),
    timeframe: str = Query(default="day", pattern="^(15minute|60minute|day)$"),
):
    """Deep scan a single symbol across all strategies."""
    broker = _get_broker()
    symbol = symbol.upper().strip()

    try:
        token, company_name = broker.get_instrument_token(symbol)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    days_back = 365 if timeframe == "day" else 30
    try:
        raw = broker.fetch_historical(token, timeframe, days_back=days_back)
        candles = broker.ohlcv_to_candles(raw)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Data fetch failed: {e}")

    if not candles:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}.")

    df = technical_service.build_dataframe(candles)

    try:
        result = screener_service.scan_symbol(symbol, df, include_fundamentals=include_fundamentals)
        result["company_name"] = company_name
        result["timeframe"] = timeframe
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/watchlist/custom")
def scan_custom_watchlist(
    symbols: List[str] = Body(..., embed=True),
    include_fundamentals: bool = Query(default=False),
    min_score: int = Query(default=50),
):
    """Scan a user-provided list of symbols."""
    if not symbols:
        raise HTTPException(status_code=400, detail="Provide at least one symbol.")
    if len(symbols) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 symbols per custom scan.")

    broker = _get_broker()
    clean_symbols = [s.upper().strip() for s in symbols]

    try:
        results = screener_service.scan_watchlist(
            clean_symbols,
            broker=broker,
            include_fundamentals=include_fundamentals,
            min_score=min_score,
        )
        return {
            "scan_type": "CUSTOM",
            "symbols_requested": len(clean_symbols),
            "candidates_found": len(results),
            "results": results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trigger/{scan_type}")
def trigger_scan(scan_type: str):
    """Manually fire a scheduled scan job: swing | intraday | premarket."""
    valid = {"swing", "intraday", "premarket"}
    if scan_type not in valid:
        raise HTTPException(status_code=400, detail=f"scan_type must be one of: {valid}")
    msg = scheduler_service.trigger_scan_now(scan_type)
    return {"triggered": scan_type, "message": msg}


@router.get("/scheduler")
def scheduler_status():
    """Show scheduled jobs and their next run times."""
    return scheduler_service.get_scheduler_status()
