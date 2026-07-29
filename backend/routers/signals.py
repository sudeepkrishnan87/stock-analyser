"""
Pending trade signal endpoints — the human approval gate for scheduler-detected
STRONG BUY + breakout setups. See docs/SECURITY.md.

  GET  /api/signals/pending                       — list signals awaiting approval
  POST /api/signals/{id}/approve                  — approve: places the real order via trading_service
  POST /api/signals/{id}/reject                   — reject: discards the signal, no order placed
  GET  /api/signals/email-action/{id}/{action}    — one-click approve/reject from an
                                                     email or WhatsApp link (token-authed,
                                                     no X-API-Key — see main.py's public
                                                     path allowlist and signal_service's
                                                     token docstring)
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

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


def _action_page(heading: str, detail: str, ok: bool) -> str:
    color = "#22c55e" if ok else "#ef4444"
    return f"""<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jarvis</title></head>
<body style="margin:0;background:#0f172a;color:#e2e8f0;font-family:Arial,sans-serif;
             display:flex;align-items:center;justify-content:center;min-height:100vh;padding:20px;">
  <div style="max-width:420px;width:100%;background:#1e293b;border:1px solid #334155;
              border-radius:12px;padding:28px;text-align:center;">
    <h2 style="margin:0 0 12px;color:{color};">{heading}</h2>
    <p style="color:#94a3b8;font-size:14px;margin:0;">{detail}</p>
  </div>
</body></html>"""


@router.get("/email-action/{signal_id}/{action}", response_class=HTMLResponse)
def email_action(signal_id: str, action: str, token: str = Query(...)):
    """
    One-click approve/reject from a link in an email or WhatsApp alert. Auth is
    the per-signal token, not X-API-Key — see signal_service._action_token's
    docstring for why, and main.py's public path allowlist for the bypass.
    """
    if action not in ("approve", "reject"):
        return HTMLResponse(_action_page("Invalid link", "Unknown action.", ok=False), status_code=400)

    if not signal_service.verify_action_token(signal_id, token):
        return HTMLResponse(
            _action_page("Invalid or expired link", "This link is not valid.", ok=False), status_code=403
        )

    result = signal_service.approve_signal(signal_id) if action == "approve" else signal_service.reject_signal(signal_id)
    status = result.get("status")

    if status == "NOT_FOUND":
        return HTMLResponse(
            _action_page("Signal not found", "It may have already expired.", ok=False), status_code=404
        )
    if status == "ALREADY_RESOLVED":
        return HTMLResponse(
            _action_page("Already resolved", result.get("reason", ""), ok=False), status_code=409
        )

    symbol = result.get("symbol", signal_id)
    if action == "approve":
        if status == "EXECUTED":
            detail = f"Order placed: qty {result.get('quantity')} @ ₹{result.get('entry_price')}"
        else:
            detail = result.get("reason", status)
        return HTMLResponse(_action_page(f"✅ Approved — {symbol}", detail, ok=(status == "EXECUTED")))

    return HTMLResponse(_action_page(f"❌ Rejected — {symbol}", "No order was placed.", ok=True))
