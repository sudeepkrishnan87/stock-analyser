"""
Trading endpoints:
  GET  /api/trading/portfolio          — live portfolio summary (P&L, positions)
  GET  /api/trading/positions          — open positions
  GET  /api/trading/history            — closed trade history
  POST /api/trading/enter              — manually enter a trade
  POST /api/trading/exit/{symbol}      — manually exit a position
  POST /api/trading/exit-all-intraday  — square off all intraday before close
  GET  /api/trading/can-trade          — check risk gates
  POST /api/trading/dry-run            — simulate a trade (no order placed)
  GET  /api/trading/broker/positions   — live positions from broker
  GET  /api/trading/broker/orders      — live orders from broker
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from config import settings
from services import trading_service

router = APIRouter()


def _get_broker():
    if not settings.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated with any broker.")
    if settings.ACTIVE_BROKER.lower() == "fyers":
        from brokers.fyers import FyersBroker
        return FyersBroker()
    from brokers.zerodha import ZerodhaBroker
    return ZerodhaBroker()


class TradeRequest(BaseModel):
    symbol: str
    direction: str = "LONG"          # LONG | SHORT
    entry_price: float
    stop_loss: float
    target: float
    trade_type: str = "SWING"        # SWING | INTRADAY
    product: str = "CNC"             # CNC | MIS


@router.get("/portfolio")
def portfolio():
    """Full portfolio snapshot including P&L at all time horizons."""
    return trading_service.portfolio_summary()


@router.get("/positions")
def open_positions():
    """List all currently open positions with live P&L."""
    state = trading_service.get_state()
    return {
        "count": len(state.positions),
        "positions": [
            {
                "symbol": sym,
                "direction": p.direction,
                "quantity": p.quantity,
                "entry_price": p.entry_price,
                "stop_loss": p.stop_loss,
                "target": p.target,
                "trade_type": p.trade_type,
                "entry_time": p.entry_time,
                "trailing_sl": p.trailing_sl,
                "trailing_activated": p.trailing_activated,
                "broker": p.broker,
                "order_id": p.order_id,
            }
            for sym, p in state.positions.items()
        ],
    }


@router.get("/history")
def trade_history(limit: int = Query(default=50, ge=1, le=200)):
    """Closed trade history, most recent first."""
    return {"trades": trading_service.get_trade_history(limit=limit)}


@router.post("/enter")
def enter_trade(req: TradeRequest):
    """Place a new trade with full risk management checks."""
    req.symbol = req.symbol.upper().strip()
    if req.direction not in ("LONG", "SHORT"):
        raise HTTPException(status_code=400, detail="direction must be LONG or SHORT")
    if req.trade_type not in ("SWING", "INTRADAY"):
        raise HTTPException(status_code=400, detail="trade_type must be SWING or INTRADAY")

    risk = abs(req.entry_price - req.stop_loss)
    reward = abs(req.target - req.entry_price)
    if risk == 0:
        raise HTTPException(status_code=400, detail="entry_price and stop_loss cannot be equal")
    if reward / risk < 1.5:
        raise HTTPException(
            status_code=400,
            detail=f"R:R ratio {reward/risk:.1f} is below minimum 1.5. Adjust target or SL.",
        )

    result = trading_service.enter_trade(
        symbol=req.symbol,
        direction=req.direction,
        entry_price=req.entry_price,
        stop_loss=req.stop_loss,
        target=req.target,
        trade_type=req.trade_type,
        product=req.product,
    )
    if result and result.get("status") in ("REJECTED", "ERROR"):
        raise HTTPException(status_code=400, detail=result.get("reason", "Trade failed"))
    return result


@router.post("/dry-run")
def dry_run_trade(req: TradeRequest):
    """Simulate a trade — calculate position size + risk without placing an order."""
    req.symbol = req.symbol.upper().strip()
    result = trading_service.enter_trade(
        symbol=req.symbol,
        direction=req.direction,
        entry_price=req.entry_price,
        stop_loss=req.stop_loss,
        target=req.target,
        trade_type=req.trade_type,
        product=req.product,
        dry_run=True,
    )
    return result


@router.post("/exit/{symbol}")
def exit_trade(symbol: str, exit_price: Optional[float] = Query(default=None)):
    """Manually exit a position. If exit_price not provided, fetches live LTP."""
    symbol = symbol.upper().strip()
    state = trading_service.get_state()

    if symbol not in state.positions:
        raise HTTPException(status_code=404, detail=f"No open position for {symbol}")

    if exit_price is None:
        try:
            broker = _get_broker()
            exit_price = broker.fetch_ltp(symbol)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Could not fetch LTP: {e}")

    result = trading_service.exit_trade(symbol, exit_price, reason="MANUAL")
    return result


@router.post("/exit-all-intraday")
def exit_all_intraday():
    """Square off all intraday (MIS) positions. Call before 3:15 PM."""
    results = trading_service.exit_all_intraday()
    return {"exited": len(results), "results": results}


@router.post("/monitor")
def monitor_positions():
    """Manually trigger position monitoring — checks SL/target for all open positions."""
    actions = trading_service.monitor_positions()
    return {"positions_checked": len(actions), "actions": actions}


@router.get("/can-trade")
def can_trade():
    """Check whether risk gates allow entering a new trade."""
    ok, reason = trading_service.can_enter_trade()
    state = trading_service.get_state()
    return {
        "can_trade": ok,
        "reason": reason if not ok else "All risk checks passed",
        "open_positions": len(state.positions),
        "max_positions": settings.MAX_OPEN_POSITIONS,
        "daily_pnl_pct": round(state.daily_pnl_pct, 2),
        "daily_loss_limit_pct": settings.DAILY_LOSS_LIMIT_PCT,
        "deployment_pct": round(state.deployment_pct, 2),
        "max_exposure_pct": settings.MAX_PORTFOLIO_EXPOSURE_PCT,
    }


@router.get("/broker/positions")
def broker_positions():
    """Fetch live positions directly from the broker."""
    try:
        broker = _get_broker()
        return {"positions": broker.get_positions()}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/broker/orders")
def broker_orders():
    """Fetch live order book directly from the broker."""
    try:
        broker = _get_broker()
        return {"orders": broker.get_orders()}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
