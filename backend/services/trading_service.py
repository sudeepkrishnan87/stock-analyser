"""
Trading engine with full risk management.

Strategy for 20% quarterly target:
  Swing: 8-15% profit target, 3-5% SL, hold 5-15 days, min 1:2 R:R
  Intraday: 1-2% profit, 0.5-0.8% SL, exit by 3:15 PM IST

Risk rules:
  - Risk at most 2% of capital per trade (position sized by SL distance)
  - Maximum 5 simultaneous positions
  - Maximum 60% of capital deployed
  - Stop all trading when daily loss ≥ 3% of capital
  - Trailing stop activated after 5% profit

Trade state persisted in data/trades.json.
"""

import json
import os
import logging
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field

import pytz

from config import settings
from brokers.base import BaseBroker
from services import alert_service

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
TRADES_FILE = os.path.join(DATA_DIR, "trades.json")
os.makedirs(DATA_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Position:
    symbol: str
    quantity: int
    entry_price: float
    stop_loss: float
    target: float
    trade_type: str          # "SWING" | "INTRADAY"
    direction: str           # "LONG" | "SHORT"
    entry_time: str          # ISO string
    order_id: str
    broker: str
    trailing_sl: float = 0.0
    trailing_activated: bool = False

    def current_pnl(self, ltp: float) -> float:
        if self.direction == "LONG":
            return (ltp - self.entry_price) * self.quantity
        return (self.entry_price - ltp) * self.quantity

    def current_pnl_pct(self, ltp: float) -> float:
        if self.entry_price == 0:
            return 0.0
        if self.direction == "LONG":
            return (ltp - self.entry_price) / self.entry_price * 100
        return (self.entry_price - ltp) / self.entry_price * 100

    def should_exit(self, ltp: float) -> Tuple[bool, str]:
        """Returns (should_exit, reason)."""
        pnl_pct = self.current_pnl_pct(ltp)

        if self.direction == "LONG":
            if ltp <= self.stop_loss:
                return True, "STOP_LOSS"
            if ltp >= self.target:
                return True, "TARGET_HIT"
            # Trailing stop: activate after 5% gain, trail at 3% below peak
            if self.trailing_sl > 0 and ltp <= self.trailing_sl:
                return True, "TRAILING_STOP"
        else:  # SHORT
            if ltp >= self.stop_loss:
                return True, "STOP_LOSS"
            if ltp <= self.target:
                return True, "TARGET_HIT"
            if self.trailing_sl > 0 and ltp >= self.trailing_sl:
                return True, "TRAILING_STOP"

        return False, ""


@dataclass
class ClosedTrade:
    symbol: str
    quantity: int
    entry_price: float
    exit_price: float
    direction: str
    trade_type: str
    entry_time: str
    exit_time: str
    pnl: float
    pnl_pct: float
    exit_reason: str
    order_id: str
    broker: str


# ─────────────────────────────────────────────────────────────────────────────
# Trade state (in-memory + persisted to JSON)
# ─────────────────────────────────────────────────────────────────────────────

class TradeState:
    def __init__(self):
        self.positions: Dict[str, Position] = {}   # symbol -> Position
        self.closed_trades: List[ClosedTrade] = []
        self.capital: float = settings.TRADING_CAPITAL
        self.realized_pnl: float = 0.0
        self._load()

    def _load(self):
        if not os.path.exists(TRADES_FILE):
            return
        try:
            with open(TRADES_FILE) as f:
                data = json.load(f)
            self.capital = data.get("capital", settings.TRADING_CAPITAL)
            self.realized_pnl = data.get("realized_pnl", 0.0)
            for sym, p in data.get("positions", {}).items():
                self.positions[sym] = Position(**p)
            for t in data.get("closed_trades", []):
                self.closed_trades.append(ClosedTrade(**t))
        except Exception as e:
            logger.warning(f"Could not load trade state: {e}")

    def save(self):
        try:
            data = {
                "capital": self.capital,
                "realized_pnl": self.realized_pnl,
                "positions": {sym: asdict(p) for sym, p in self.positions.items()},
                "closed_trades": [asdict(t) for t in self.closed_trades[-500:]],  # keep last 500
            }
            with open(TRADES_FILE, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Could not save trade state: {e}")

    @property
    def daily_pnl(self) -> float:
        today = date.today().isoformat()
        return sum(
            t.pnl for t in self.closed_trades
            if t.exit_time.startswith(today)
        )

    @property
    def daily_pnl_pct(self) -> float:
        return self.daily_pnl / self.capital * 100 if self.capital > 0 else 0

    @property
    def deployed_capital(self) -> float:
        return sum(p.quantity * p.entry_price for p in self.positions.values())

    @property
    def deployment_pct(self) -> float:
        return self.deployed_capital / self.capital * 100 if self.capital > 0 else 0

    @property
    def unrealized_pnl(self) -> float:
        return sum(p.current_pnl(p.entry_price) for p in self.positions.values())

    def win_rate(self) -> float:
        if not self.closed_trades:
            return 0.0
        wins = sum(1 for t in self.closed_trades if t.pnl > 0)
        return wins / len(self.closed_trades) * 100

    def qtd_pnl(self) -> float:
        """Quarter-to-date realized P&L."""
        now = datetime.now(IST)
        q_start_month = ((now.month - 1) // 3) * 3 + 1
        q_start = date(now.year, q_start_month, 1).isoformat()
        return sum(t.pnl for t in self.closed_trades if t.exit_time >= q_start)

    def mtd_pnl(self) -> float:
        now = datetime.now(IST)
        m_start = date(now.year, now.month, 1).isoformat()
        return sum(t.pnl for t in self.closed_trades if t.exit_time >= m_start)


_state = TradeState()


def get_state() -> TradeState:
    return _state


# ─────────────────────────────────────────────────────────────────────────────
# Core trading functions
# ─────────────────────────────────────────────────────────────────────────────

def _get_broker() -> BaseBroker:
    broker_name = settings.ACTIVE_BROKER.lower()
    if broker_name == "fyers":
        from brokers.fyers import FyersBroker
        return FyersBroker()
    from brokers.zerodha import ZerodhaBroker
    return ZerodhaBroker()


def calculate_position_size(entry: float, stop_loss: float) -> int:
    """
    Risk-based position sizing.
    Risk amount = 2% of capital.
    Shares = risk_amount / (entry - stop_loss)
    Capped at max_exposure_pct of capital.
    """
    risk_amount = _state.capital * (settings.MAX_RISK_PER_TRADE_PCT / 100)
    risk_per_share = abs(entry - stop_loss)
    if risk_per_share < 0.01:
        return 0
    shares = int(risk_amount / risk_per_share)

    # Cap so total deployment stays within limit
    max_deployable = _state.capital * (settings.MAX_PORTFOLIO_EXPOSURE_PCT / 100) - _state.deployed_capital
    if max_deployable <= 0:
        return 0
    shares = min(shares, int(max_deployable / entry))
    return max(0, shares)


def can_enter_trade() -> Tuple[bool, str]:
    if len(_state.positions) >= settings.MAX_OPEN_POSITIONS:
        return False, f"Max {settings.MAX_OPEN_POSITIONS} positions already open."
    if _state.daily_pnl_pct <= -(settings.DAILY_LOSS_LIMIT_PCT):
        return False, f"Daily loss limit {settings.DAILY_LOSS_LIMIT_PCT}% reached."
    if _state.deployment_pct >= settings.MAX_PORTFOLIO_EXPOSURE_PCT:
        return False, "Max portfolio exposure reached."
    return True, "OK"


def enter_trade(
    symbol: str,
    direction: str,          # "LONG" | "SHORT"
    entry_price: float,
    stop_loss: float,
    target: float,
    trade_type: str,         # "SWING" | "INTRADAY"
    product: str = "CNC",   # CNC for swing, MIS for intraday
    dry_run: bool = False,
) -> Optional[Dict]:
    """
    Enter a trade with full risk management.
    dry_run=True simulates the order without placing it.
    """
    ok, reason = can_enter_trade()
    if not ok:
        logger.warning(f"Cannot enter trade for {symbol}: {reason}")
        return {"status": "REJECTED", "reason": reason}

    if symbol in _state.positions:
        return {"status": "REJECTED", "reason": f"Already in position for {symbol}"}

    # Validate R:R
    risk = abs(entry_price - stop_loss)
    reward = abs(target - entry_price)
    rr = reward / risk if risk > 0 else 0
    if rr < 1.5:
        return {"status": "REJECTED", "reason": f"R:R ratio {rr:.1f} below minimum 1.5"}

    quantity = calculate_position_size(entry_price, stop_loss)
    if quantity == 0:
        return {"status": "REJECTED", "reason": "Position size is 0. Check capital or exposure."}

    if dry_run:
        return {
            "status": "DRY_RUN",
            "symbol": symbol,
            "direction": direction,
            "quantity": quantity,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "target": target,
            "trade_type": trade_type,
            "risk_amount": round(quantity * risk, 2),
            "max_profit": round(quantity * reward, 2),
            "rr_ratio": round(rr, 2),
        }

    broker = _get_broker()
    tx_type = "BUY" if direction == "LONG" else "SELL"
    try:
        order = broker.place_order(
            symbol=symbol,
            transaction_type=tx_type,
            quantity=quantity,
            order_type="MARKET",
            product=product,
        )
    except Exception as e:
        logger.error(f"Order placement failed: {e}")
        return {"status": "ERROR", "reason": str(e)}

    if not order:
        return {"status": "ERROR", "reason": "Broker returned no order confirmation."}

    position = Position(
        symbol=symbol,
        quantity=quantity,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target=target,
        trade_type=trade_type,
        direction=direction,
        entry_time=datetime.now(IST).isoformat(),
        order_id=order.get("order_id", ""),
        broker=order.get("broker", ""),
    )
    _state.positions[symbol] = position
    _state.save()

    alert_service.alert_trade_executed(symbol, tx_type, quantity, entry_price, position.order_id)

    logger.info(f"Entered {direction} {symbol}: qty={quantity}, entry={entry_price}, sl={stop_loss}, target={target}")
    return {
        "status": "EXECUTED",
        "symbol": symbol,
        "direction": direction,
        "quantity": quantity,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "target": target,
        "order_id": position.order_id,
        "risk_amount": round(quantity * risk, 2),
        "max_profit": round(quantity * reward, 2),
        "rr_ratio": round(rr, 2),
    }


def exit_trade(symbol: str, exit_price: float, reason: str = "MANUAL") -> Optional[Dict]:
    """Exit a position. reason: STOP_LOSS | TARGET_HIT | TRAILING_STOP | MANUAL | EOD."""
    if symbol not in _state.positions:
        return {"status": "ERROR", "reason": f"No open position for {symbol}"}

    pos = _state.positions[symbol]
    broker = _get_broker()

    tx_type = "SELL" if pos.direction == "LONG" else "BUY"
    try:
        order = broker.place_order(
            symbol=symbol,
            transaction_type=tx_type,
            quantity=pos.quantity,
            order_type="MARKET",
            product="CNC" if pos.trade_type == "SWING" else "MIS",
        )
    except Exception as e:
        logger.error(f"Exit order failed for {symbol}: {e}")
        return {"status": "ERROR", "reason": str(e)}

    pnl = pos.current_pnl(exit_price)
    pnl_pct = pos.current_pnl_pct(exit_price)

    closed = ClosedTrade(
        symbol=symbol,
        quantity=pos.quantity,
        entry_price=pos.entry_price,
        exit_price=exit_price,
        direction=pos.direction,
        trade_type=pos.trade_type,
        entry_time=pos.entry_time,
        exit_time=datetime.now(IST).isoformat(),
        pnl=round(pnl, 2),
        pnl_pct=round(pnl_pct, 2),
        exit_reason=reason,
        order_id=order.get("order_id", "") if order else "",
        broker=pos.broker,
    )
    _state.closed_trades.append(closed)
    _state.realized_pnl += pnl
    del _state.positions[symbol]
    _state.save()

    # Send alert based on exit reason
    if reason == "STOP_LOSS":
        alert_service.alert_stop_loss_hit(symbol, pos.entry_price, exit_price, abs(pnl_pct))
    elif reason == "TARGET_HIT":
        alert_service.alert_target_hit(symbol, pos.entry_price, exit_price, pnl_pct)

    logger.info(f"Exited {symbol}: pnl=₹{pnl:.2f} ({pnl_pct:.2f}%), reason={reason}")
    return {
        "status": "CLOSED",
        "symbol": symbol,
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
        "exit_reason": reason,
    }


def monitor_positions() -> List[Dict]:
    """
    Check all open positions against current LTP.
    Trigger SL/target exits and update trailing stops.
    Call this every 5 minutes during market hours.
    """
    if not _state.positions:
        return []

    broker = _get_broker()
    actions = []

    for symbol, pos in list(_state.positions.items()):
        try:
            ltp = broker.fetch_ltp(symbol)
        except Exception as e:
            logger.warning(f"LTP fetch failed for {symbol}: {e}")
            continue

        # Update trailing stop after 5% gain
        pnl_pct = pos.current_pnl_pct(ltp)
        if pnl_pct >= 5.0 and not pos.trailing_activated:
            if pos.direction == "LONG":
                pos.trailing_sl = round(ltp * 0.97, 2)   # 3% below current
            else:
                pos.trailing_sl = round(ltp * 1.03, 2)
            pos.trailing_activated = True
            logger.info(f"Trailing stop activated for {symbol} at {pos.trailing_sl}")
        elif pos.trailing_activated:
            # Move trailing stop up (for LONG) or down (for SHORT)
            if pos.direction == "LONG":
                new_trail = round(ltp * 0.97, 2)
                if new_trail > pos.trailing_sl:
                    pos.trailing_sl = new_trail
            else:
                new_trail = round(ltp * 1.03, 2)
                if new_trail < pos.trailing_sl:
                    pos.trailing_sl = new_trail

        should_exit, reason = pos.should_exit(ltp)
        if should_exit:
            result = exit_trade(symbol, ltp, reason)
            actions.append({"symbol": symbol, "action": "EXIT", "reason": reason, "ltp": ltp, "result": result})
        else:
            actions.append({"symbol": symbol, "action": "HOLD", "ltp": ltp, "pnl_pct": round(pnl_pct, 2)})

    _state.save()
    return actions


def exit_all_intraday() -> List[Dict]:
    """Exit all INTRADAY positions. Call at 3:15 PM IST."""
    results = []
    broker = _get_broker()
    for symbol, pos in list(_state.positions.items()):
        if pos.trade_type == "INTRADAY":
            try:
                ltp = broker.fetch_ltp(symbol)
            except Exception:
                ltp = pos.entry_price
            result = exit_trade(symbol, ltp, "EOD")
            results.append(result)
    return results


def portfolio_summary() -> Dict:
    now_ist = datetime.now(IST)
    return {
        "capital": round(_state.capital, 2),
        "deployed_capital": round(_state.deployed_capital, 2),
        "deployment_pct": round(_state.deployment_pct, 2),
        "open_positions": len(_state.positions),
        "positions": [asdict(p) for p in _state.positions.values()],
        "realized_pnl": round(_state.realized_pnl, 2),
        "daily_pnl": round(_state.daily_pnl, 2),
        "daily_pnl_pct": round(_state.daily_pnl_pct, 2),
        "mtd_pnl": round(_state.mtd_pnl(), 2),
        "mtd_pnl_pct": round(_state.mtd_pnl() / _state.capital * 100, 2),
        "qtd_pnl": round(_state.qtd_pnl(), 2),
        "qtd_pnl_pct": round(_state.qtd_pnl() / _state.capital * 100, 2),
        "total_trades": len(_state.closed_trades),
        "win_rate": round(_state.win_rate(), 1),
        "can_trade": can_enter_trade()[0],
        "trade_block_reason": can_enter_trade()[1] if not can_enter_trade()[0] else None,
        "timestamp": now_ist.strftime("%Y-%m-%d %H:%M:%S IST"),
    }


def get_trade_history(limit: int = 50) -> List[Dict]:
    trades = sorted(_state.closed_trades, key=lambda t: t.exit_time, reverse=True)
    return [asdict(t) for t in trades[:limit]]
