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
from services import alert_service, backup_service

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
    # Reasoning captured at entry — why this trade was taken, not just its
    # mechanics. Defaults keep old trades.json entries (before this field
    # existed) loadable without a migration.
    signal_score: float = 0.0
    source: str = "MANUAL"    # PREMARKET | INTRADAY | SWING | MANUAL
    reason: str = ""          # breakout description or score-based summary
    risk_amount: float = 0.0  # ₹ actually at risk (quantity * |entry - stop_loss|)
    capital_at_entry: float = 0.0  # _state.capital when sized, so the 2% risk math is auditable later
    partial_exit_done: bool = False  # True once the 50% target-hit profit booking has fired

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
        """
        Returns (should_exit, reason). Once the target has already triggered
        a partial (50%) exit, the original target no longer closes the
        remainder — the runner is governed purely by stop_loss (moved to
        breakeven-or-better at that point) and the trailing stop, so it can
        keep capturing upside instead of being capped at the first target.
        """
        if self.direction == "LONG":
            if ltp <= self.stop_loss:
                return True, "STOP_LOSS"
            if not self.partial_exit_done and ltp >= self.target:
                return True, "TARGET_HIT"
            # Trailing stop: activate after 5% gain, trail at 3% below peak
            if self.trailing_sl > 0 and ltp <= self.trailing_sl:
                return True, "TRAILING_STOP"
        else:  # SHORT
            if ltp >= self.stop_loss:
                return True, "STOP_LOSS"
            if not self.partial_exit_done and ltp <= self.target:
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
    # Same reasoning fields as Position — carried through on close so closed
    # trades stay analyzable (which scores/sources actually performed).
    signal_score: float = 0.0
    source: str = "MANUAL"
    reason: str = ""
    risk_amount: float = 0.0
    capital_at_entry: float = 0.0


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
        backup_service.restore_trades_file_if_missing(TRADES_FILE)
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
            backup_service.backup_trades_file(TRADES_FILE)
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


def calculate_position_size(entry: float, stop_loss: float, broker: Optional[BaseBroker] = None) -> int:
    """
    Risk-based position sizing.
    Risk amount = 2% of capital.
    Shares = risk_amount / (entry - stop_loss)
    Capped at max_exposure_pct of capital, and — if a broker is passed —
    additionally capped at real available funds in the account, so sizing
    never assumes cash that isn't actually there. Failure to fetch funds
    (transient API issue) falls back to the configured-capital-only cap
    rather than blocking the trade.
    """
    risk_amount = _state.capital * (settings.MAX_RISK_PER_TRADE_PCT / 100)
    risk_per_share = abs(entry - stop_loss)
    if risk_per_share < 0.01:
        return 0
    shares = int(risk_amount / risk_per_share)

    # Cap so total deployment stays within the configured limit
    max_deployable = _state.capital * (settings.MAX_PORTFOLIO_EXPOSURE_PCT / 100) - _state.deployed_capital
    if max_deployable <= 0:
        return 0
    shares = min(shares, int(max_deployable / entry))

    if broker is not None:
        try:
            available_funds = broker.get_available_funds()
            shares = min(shares, int(available_funds / entry))
        except Exception as e:
            logger.warning(f"Could not fetch available funds — sizing off configured capital only: {e}")

    return max(0, shares)


# Used only when real broker funds can't be determined (not authenticated, API
# error, or a genuinely empty account) — an illustrative stand-in so a signal
# still shows *some* quantity estimate instead of a bare 0, per the operator's
# explicit request. Not tied to settings.TRADING_CAPITAL, which is the real
# persisted figure — this is deliberately a fixed placeholder.
HYPOTHETICAL_CAPITAL = 10_000.0


def estimate_quantity(entry_price: float, stop_loss: float) -> Dict:
    """
    Preview how many shares the 2%-risk sizing formula would actually buy
    right now, without placing anything — same math calculate_position_size()
    uses at real order time, surfaced for display in alerts/the Signals tab
    so the likely fill size is visible before approving. Falls back to a
    clearly-labeled hypothetical ₹10,000 balance if real available funds
    can't be fetched.
    """
    broker = None
    available_funds = 0.0
    try:
        broker = _get_broker()
        available_funds = broker.get_available_funds()
    except Exception as e:
        logger.warning(f"Could not fetch available funds for quantity estimate: {e}")

    if available_funds and available_funds > 0:
        qty = calculate_position_size(entry_price, stop_loss, broker=broker)
        return {
            "quantity": qty,
            "investment": round(qty * entry_price, 2),
            "available_funds": round(available_funds, 2),
            "is_hypothetical": False,
        }

    risk_amount = HYPOTHETICAL_CAPITAL * (settings.MAX_RISK_PER_TRADE_PCT / 100)
    risk_per_share = abs(entry_price - stop_loss)
    qty = 0
    if risk_per_share >= 0.01 and entry_price > 0:
        qty = int(risk_amount / risk_per_share)
        max_deployable = HYPOTHETICAL_CAPITAL * (settings.MAX_PORTFOLIO_EXPOSURE_PCT / 100)
        qty = max(0, min(qty, int(max_deployable / entry_price)))
    return {
        "quantity": qty,
        "investment": round(qty * entry_price, 2),
        "available_funds": HYPOTHETICAL_CAPITAL,
        "is_hypothetical": True,
    }


def _round_to_tick(price: float, tick: float = 0.05) -> float:
    """NSE equity tick size is 0.05 — snap to the nearest valid tick or the broker rejects the order."""
    return round(round(price / tick) * tick, 2)


# Marketable-limit buffer beyond live LTP — Zerodha's API rejects plain MARKET
# orders ("market protection" restriction, see docs/TRADING_LOGIC.md §4), so
# every order is placed as a LIMIT order priced just past LTP instead. Wide
# enough to fill immediately in normal liquidity, tight enough to bound
# worst-case slippage.
LIMIT_ORDER_BUFFER_PCT = 0.25


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
    signal_score: float = 0.0,
    source: str = "MANUAL",
    reason: str = "",
) -> Optional[Dict]:
    """
    Enter a trade with full risk management.
    dry_run=True simulates the order without placing it.
    signal_score/source/reason are purely for the trade book's record of *why*
    this trade was taken — approve_signal() passes the originating signal's
    values; callers with no signal context (manual entry) leave the defaults.
    """
    ok, block_reason = can_enter_trade()
    if not ok:
        logger.warning(f"Cannot enter trade for {symbol}: {block_reason}")
        return {"status": "REJECTED", "reason": block_reason}

    if symbol in _state.positions:
        return {"status": "REJECTED", "reason": f"Already in position for {symbol}"}

    # Validate R:R
    risk = abs(entry_price - stop_loss)
    reward = abs(target - entry_price)
    rr = reward / risk if risk > 0 else 0
    if rr < 1.5:
        return {"status": "REJECTED", "reason": f"R:R ratio {rr:.1f} below minimum 1.5"}

    broker = _get_broker()
    quantity = calculate_position_size(entry_price, stop_loss, broker=broker)
    if quantity == 0:
        return {"status": "REJECTED", "reason": "Position size is 0. Check capital, exposure, or available funds."}

    tx_type = "BUY" if direction == "LONG" else "SELL"

    # Price the marketable LIMIT order off live LTP, not the signal's (possibly
    # stale, up to ~24h old for swing) entry_price — falls back to entry_price
    # only if the live quote fetch itself fails.
    try:
        ltp = broker.fetch_ltp(symbol)
    except Exception as e:
        logger.warning(f"Could not fetch LTP for {symbol}, using signal entry price instead: {e}")
        ltp = entry_price
    buffer_mult = 1 + LIMIT_ORDER_BUFFER_PCT / 100 if tx_type == "BUY" else 1 - LIMIT_ORDER_BUFFER_PCT / 100
    limit_price = _round_to_tick(ltp * buffer_mult)

    if dry_run:
        return {
            "status": "DRY_RUN",
            "symbol": symbol,
            "direction": direction,
            "quantity": quantity,
            "entry_price": entry_price,
            "limit_price": limit_price,
            "stop_loss": stop_loss,
            "target": target,
            "trade_type": trade_type,
            "risk_amount": round(quantity * risk, 2),
            "max_profit": round(quantity * reward, 2),
            "rr_ratio": round(rr, 2),
        }

    try:
        order = broker.place_order(
            symbol=symbol,
            transaction_type=tx_type,
            quantity=quantity,
            order_type="LIMIT",
            price=limit_price,
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
        entry_price=limit_price,
        stop_loss=stop_loss,
        target=target,
        trade_type=trade_type,
        direction=direction,
        entry_time=datetime.now(IST).isoformat(),
        order_id=order.get("order_id", ""),
        broker=order.get("broker", ""),
        signal_score=signal_score,
        source=source,
        reason=reason,
        risk_amount=round(quantity * risk, 2),
        capital_at_entry=round(_state.capital, 2),
    )
    _state.positions[symbol] = position
    _state.save()

    alert_service.alert_trade_executed(symbol, tx_type, quantity, limit_price, position.order_id)

    logger.info(f"Entered {direction} {symbol}: qty={quantity}, limit={limit_price}, sl={stop_loss}, target={target}")
    return {
        "status": "EXECUTED",
        "symbol": symbol,
        "direction": direction,
        "quantity": quantity,
        "entry_price": limit_price,
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
    # Same Zerodha "market protection" restriction as enter_trade() — a bare
    # MARKET order is rejected by the API. exit_price is already a fresh LTP
    # from the caller (monitor_positions / exit_all_intraday), so price the
    # marketable LIMIT directly off it rather than re-fetching.
    buffer_mult = 1 + LIMIT_ORDER_BUFFER_PCT / 100 if tx_type == "BUY" else 1 - LIMIT_ORDER_BUFFER_PCT / 100
    exit_limit_price = _round_to_tick(exit_price * buffer_mult)
    try:
        order = broker.place_order(
            symbol=symbol,
            transaction_type=tx_type,
            quantity=pos.quantity,
            order_type="LIMIT",
            price=exit_limit_price,
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
        signal_score=pos.signal_score,
        source=pos.source,
        reason=pos.reason,
        risk_amount=pos.risk_amount,
        capital_at_entry=pos.capital_at_entry,
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


def _partial_exit_target(symbol: str, exit_price: float) -> Optional[Dict]:
    """
    Target hit: book half the position now, lock that profit in as a closed
    trade, and let the other half keep running — protected by moving its
    stop-loss up to breakeven (never worse) and arming the trailing stop at
    the current price. If the position is too small to split, falls back to
    a full exit instead.
    """
    if symbol not in _state.positions:
        return None
    pos = _state.positions[symbol]

    half_qty = pos.quantity // 2
    if half_qty == 0:
        return exit_trade(symbol, exit_price, "TARGET_HIT")

    broker = _get_broker()
    tx_type = "SELL" if pos.direction == "LONG" else "BUY"
    buffer_mult = 1 + LIMIT_ORDER_BUFFER_PCT / 100 if tx_type == "BUY" else 1 - LIMIT_ORDER_BUFFER_PCT / 100
    exit_limit_price = _round_to_tick(exit_price * buffer_mult)
    try:
        order = broker.place_order(
            symbol=symbol,
            transaction_type=tx_type,
            quantity=half_qty,
            order_type="LIMIT",
            price=exit_limit_price,
            product="CNC" if pos.trade_type == "SWING" else "MIS",
        )
    except Exception as e:
        logger.error(f"Partial exit order failed for {symbol}: {e}")
        return {"status": "ERROR", "reason": str(e)}

    per_share = (exit_price - pos.entry_price) if pos.direction == "LONG" else (pos.entry_price - exit_price)
    pnl = per_share * half_qty
    pnl_pct = pos.current_pnl_pct(exit_price)

    closed = ClosedTrade(
        symbol=symbol,
        quantity=half_qty,
        entry_price=pos.entry_price,
        exit_price=exit_price,
        direction=pos.direction,
        trade_type=pos.trade_type,
        entry_time=pos.entry_time,
        exit_time=datetime.now(IST).isoformat(),
        pnl=round(pnl, 2),
        pnl_pct=round(pnl_pct, 2),
        exit_reason="PARTIAL_TARGET_50PCT",
        order_id=order.get("order_id", "") if order else "",
        broker=pos.broker,
        signal_score=pos.signal_score,
        source=pos.source,
        reason=pos.reason,
        risk_amount=pos.risk_amount,
        capital_at_entry=pos.capital_at_entry,
    )
    _state.closed_trades.append(closed)
    _state.realized_pnl += pnl

    pos.quantity -= half_qty
    pos.partial_exit_done = True
    if pos.direction == "LONG":
        pos.stop_loss = max(pos.stop_loss, pos.entry_price)
        pos.trailing_sl = round(exit_price * 0.97, 2)
    else:
        pos.stop_loss = min(pos.stop_loss, pos.entry_price)
        pos.trailing_sl = round(exit_price * 1.03, 2)
    pos.trailing_activated = True
    _state.save()

    alert_service.alert_partial_target_hit(
        symbol, pos.entry_price, exit_price, pnl_pct,
        qty_closed=half_qty, qty_remaining=pos.quantity, new_stop_loss=pos.stop_loss,
    )

    logger.info(
        f"Partial target exit {symbol}: booked {half_qty} @ {exit_price} (pnl=₹{pnl:.2f}); "
        f"{pos.quantity} left, SL now {pos.stop_loss}, trailing {pos.trailing_sl}"
    )
    return {
        "status": "PARTIAL_CLOSED",
        "symbol": symbol,
        "qty_closed": half_qty,
        "qty_remaining": pos.quantity,
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
        "exit_reason": "PARTIAL_TARGET_50PCT",
        "new_stop_loss": pos.stop_loss,
        "new_trailing_sl": pos.trailing_sl,
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
            if reason == "TARGET_HIT":
                result = _partial_exit_target(symbol, ltp)
                actions.append({"symbol": symbol, "action": "PARTIAL_EXIT", "reason": reason, "ltp": ltp, "result": result})
            else:
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
