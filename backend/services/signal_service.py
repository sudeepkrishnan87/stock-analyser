"""
Pending trade signals awaiting human approval.

Every scan job (premarket, intraday, swing) that finds a BUY/STRONG BUY with a
viable trade_suggestion queues it here instead of entering it automatically
(see docs/SECURITY.md — "no global paper-trading switch" finding). Nothing in
this module talks to a broker; approve_signal() is the only bridge into
trading_service.enter_trade(), and it only ever runs when a human calls it
explicitly via POST /api/signals/{id}/approve.

In-memory only, by design: even the longest-lived signals (swing, ~24h) don't
need to survive a process restart the way trades.json does.
"""

import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pytz

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

# Default TTL for intraday signals — matches the 15-min scan cadence, i.e. a
# signal is expected to be superseded or acted on before the next tick.
SIGNAL_TTL_MINUTES = 20


@dataclass
class PendingSignal:
    id: str
    symbol: str
    signal: str
    signal_score: float
    entry: float
    stop_loss: float
    target: float
    rr_ratio: float
    trade_type: str            # INTRADAY | SWING — decides product (MIS/CNC) on approval
    source: str                # PREMARKET | INTRADAY | SWING — which scan found it
    breakout_signal: Optional[str]
    created_at: str
    expires_at: str
    status: str = "PENDING"   # PENDING | APPROVED | REJECTED | EXPIRED
    resolution: Optional[Dict] = None


_pending: Dict[str, PendingSignal] = {}


def add_pending_signal(
    symbol: str,
    signal: str,
    signal_score: float,
    trade_suggestion: dict,
    source: str = "INTRADAY",
    breakout_signal: Optional[str] = None,
    ttl_minutes: Optional[int] = None,
) -> PendingSignal:
    """Queue a signal for approval, replacing any still-pending one for the same symbol."""
    for sid, s in list(_pending.items()):
        if s.symbol == symbol and s.status == "PENDING":
            del _pending[sid]

    now = datetime.now(IST)
    ttl = ttl_minutes if ttl_minutes is not None else SIGNAL_TTL_MINUTES
    sig = PendingSignal(
        id=uuid.uuid4().hex[:10],
        symbol=symbol,
        signal=signal,
        signal_score=signal_score,
        entry=trade_suggestion["entry"],
        stop_loss=trade_suggestion["stop_loss"],
        target=trade_suggestion["target"],
        rr_ratio=trade_suggestion.get("rr_ratio", 0),
        trade_type=trade_suggestion.get("trade_type", "INTRADAY"),
        source=source,
        breakout_signal=breakout_signal,
        created_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=ttl)).isoformat(),
    )
    _pending[sig.id] = sig
    logger.info(f"[SIGNALS] Queued {symbol} for approval ({source}, {signal}, score {signal_score})")
    return sig


def _expire_stale() -> None:
    now = datetime.now(IST)
    for s in _pending.values():
        if s.status == "PENDING" and datetime.fromisoformat(s.expires_at) < now:
            s.status = "EXPIRED"


def list_pending_signals() -> List[dict]:
    _expire_stale()
    return [asdict(s) for s in _pending.values() if s.status == "PENDING"]


def count_pending() -> int:
    _expire_stale()
    return sum(1 for s in _pending.values() if s.status == "PENDING")


def approve_signal(signal_id: str) -> dict:
    from services import trading_service

    _expire_stale()
    sig = _pending.get(signal_id)
    if not sig:
        return {"status": "NOT_FOUND", "reason": "Signal not found."}
    if sig.status != "PENDING":
        return {"status": "ALREADY_RESOLVED", "reason": f"Signal already {sig.status.lower()}."}

    result = trading_service.enter_trade(
        symbol=sig.symbol,
        direction="LONG",
        entry_price=sig.entry,
        stop_loss=sig.stop_loss,
        target=sig.target,
        trade_type=sig.trade_type,
        product="MIS" if sig.trade_type == "INTRADAY" else "CNC",
    )
    sig.status = "APPROVED"
    sig.resolution = result
    logger.info(f"[SIGNALS] Approved {sig.symbol}: {(result or {}).get('status')}")
    return result


def reject_signal(signal_id: str) -> dict:
    _expire_stale()
    sig = _pending.get(signal_id)
    if not sig:
        return {"status": "NOT_FOUND", "reason": "Signal not found."}
    if sig.status != "PENDING":
        return {"status": "ALREADY_RESOLVED", "reason": f"Signal already {sig.status.lower()}."}
    sig.status = "REJECTED"
    logger.info(f"[SIGNALS] Rejected {sig.symbol}")
    return {"status": "REJECTED", "symbol": sig.symbol}
