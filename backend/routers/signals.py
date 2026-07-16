"""
Pending trade signal endpoints — the human approval gate for scheduler-detected
STRONG BUY + breakout setups. See docs/SECURITY.md.

  GET  /api/signals/pending        — list signals awaiting approval
  POST /api/signals/{id}/approve   — approve: places the real order via trading_service
  POST /api/signals/{id}/reject    — reject: discards the signal, no order placed
"""

from fastapi import APIRouter, HTTPException

from services import signal_service

router = APIRouter()

_ERROR_STATUS_CODES = {"NOT_FOUND": 404, "ALREADY_RESOLVED": 409}


@router.get("/pending")
def pending_signals():
    signals = signal_service.list_pending_signals()
    return {"count": len(signals), "signals": signals}


@router.post("/{signal_id}/approve")
def approve(signal_id: str):
    result = signal_service.approve_signal(signal_id)
    code = _ERROR_STATUS_CODES.get(result.get("status"))
    if code:
        raise HTTPException(status_code=code, detail=result["reason"])
    return result


@router.post("/{signal_id}/reject")
def reject(signal_id: str):
    result = signal_service.reject_signal(signal_id)
    code = _ERROR_STATUS_CODES.get(result.get("status"))
    if code:
        raise HTTPException(status_code=code, detail=result["reason"])
    return result
