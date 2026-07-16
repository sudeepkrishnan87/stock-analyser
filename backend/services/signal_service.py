"""
Pending trade signals awaiting human approval.

The scheduler's intraday scan surfaces STRONG BUY + confirmed-breakout candidates
here instead of entering them automatically (see docs/SECURITY.md — "no global
paper-trading switch" finding). Nothing in this module talks to a broker;
approve_signal() is the only bridge into trading_service.enter_trade(), and it
only ever runs when a human calls it explicitly via POST /api/signals/{id}/approve.

In-memory only, by design: signals are intraday and expire in minutes, so there's
nothing worth surviving a process restart (unlike trades.json).
"""

import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pytz

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

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
    breakout_signal: Optional[str] = None,
) -> PendingSignal:
    """Queue a signal for approval, replacing any still-pending one for the same symbol."""
    for sid, s in list(_pending.items()):
        if s.symbol == symbol and s.status == "PENDING":
            del _pending[sid]

    now = datetime.now(IST)
    sig = PendingSignal(
        id=uuid.uuid4().hex[:10],
        symbol=symbol,
        signal=signal,
        signal_score=signal_score,
        entry=trade_suggestion["entry"],
        stop_loss=trade_suggestion["stop_loss"],
        target=trade_suggestion["target"],
        rr_ratio=trade_suggestion.get("rr_ratio", 0),
        breakout_signal=breakout_signal,
        created_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=SIGNAL_TTL_MINUTES)).isoformat(),
    )
    _pending[sig.id] = sig
    logger.info(f"[SIGNALS] Queued {symbol} for approval ({signal}, score {signal_score})")
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
        trade_type="INTRADAY",
        product="MIS",
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
