from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from schemas import TokenRequest, TokenStatus
from config import settings
from kiteconnect import KiteConnect

router = APIRouter()


# ═════════════════════════════════════════════════════════════════
#  Zerodha (Kite) auth
#
#  Flow:
#   1. GET  /api/auth/login-url   → open URL in browser
#   2. User logs in → Kite redirects to KITE_REDIRECT_URL?request_token=XXX
#   3. GET  /api/auth/callback    → auto-exchanges request_token for access_token
#   4. Done — token stored in memory
#
#  Kite developer console  (https://developers.kite.trade/apps):
#    Redirect URL → https://xxxx.ngrok-free.app/api/auth/callback
#    (same URL for both local dev via ngrok and AWS production)
# ═════════════════════════════════════════════════════════════════

@router.get("/status", response_model=TokenStatus)
def get_auth_status():
    return TokenStatus(
        authenticated=settings.is_authenticated(),
        message="Token active" if settings.is_authenticated() else "No token set",
    )


@router.get("/login-url")
def get_login_url():
    """
    Step 1: Call this to get the Kite login URL.
    Open it in your browser → log in → Zerodha redirects automatically
    to /api/auth/callback which completes auth without any manual steps.
    """
    if not settings.KITE_API_KEY:
        raise HTTPException(status_code=500, detail="KITE_API_KEY not configured. Check .env.")
    kite = KiteConnect(api_key=settings.KITE_API_KEY)
    return {
        "login_url": kite.login_url(),
        "instructions": (
            "Open login_url in your browser. After login, Zerodha will redirect "
            "to your callback URL automatically and the token will be set."
        ),
    }


@router.get("/callback", response_class=HTMLResponse)
def kite_callback(
    request_token: str = Query(...),
    status: str = Query(default="success"),
):
    """
    Step 2 (auto): Zerodha redirects here after login with ?request_token=XXX
    Exchanges the request_token + API secret for a usable access_token.
    """
    if status != "success":
        return HTMLResponse(
            content=_html_page("error", f"Zerodha login failed. Status: {status}"),
            status_code=401,
        )
    if not settings.KITE_API_KEY or not settings.KITE_API_SECRET:
        return HTMLResponse(
            content=_html_page("error", "KITE_API_KEY or KITE_API_SECRET not set in .env"),
            status_code=500,
        )
    try:
        kite = KiteConnect(api_key=settings.KITE_API_KEY)
        session_data = kite.generate_session(request_token, api_secret=settings.KITE_API_SECRET)
        access_token = session_data["access_token"]
        kite.set_access_token(access_token)
        profile = kite.profile()
        settings.set_access_token(access_token)
        name = profile.get("user_name", "User")
        uid = profile.get("user_id", "")
        return HTMLResponse(
            content=_html_page("success", f"Zerodha authenticated as <b>{name}</b> ({uid}).<br>You can close this tab.")
        )
    except Exception as e:
        return HTMLResponse(
            content=_html_page("error", f"Token exchange failed: {e}"),
            status_code=500,
        )


@router.post("/token", response_model=TokenStatus)
def set_access_token_manual(body: TokenRequest):
    """
    Fallback: paste a Zerodha access token manually.
    Use this only if the automatic callback isn't reachable.
    """
    token = body.access_token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Access token cannot be empty.")
    if not settings.KITE_API_KEY:
        raise HTTPException(status_code=500, detail="KITE_API_KEY not configured. Check .env.")
    try:
        kite = KiteConnect(api_key=settings.KITE_API_KEY)
        kite.set_access_token(token)
        profile = kite.profile()
        settings.set_access_token(token)
        return TokenStatus(
            authenticated=True,
            message=f"Authenticated as {profile.get('user_name', 'User')} ({profile.get('user_id', '')})",
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Kite access token: {e}")


@router.delete("/token", response_model=TokenStatus)
def clear_access_token():
    settings.clear_token()
    return TokenStatus(authenticated=False, message="Token cleared.")


@router.get("/exchange")
def exchange_request_token(request_token: str = Query(...)):
    """
    Manually exchange a Zerodha request_token for an access_token.

    Use this when the redirect URL is not yet reachable (e.g. AWS not deployed yet).

    How to use:
      1. Open the login URL from /api/auth/login-url in your browser
      2. Log in with Zerodha credentials
      3. Browser redirects to your redirect URL — if it fails to load,
         copy the full URL from the address bar. It looks like:
         http://localhost:8000/api/auth/callback?request_token=XXXXX&status=success
      4. Copy just the request_token value (XXXXX)
      5. Call: GET /api/auth/exchange?request_token=XXXXX
      6. Done — token is set and Jarvis is authenticated
    """
    if not settings.KITE_API_KEY or not settings.KITE_API_SECRET:
        raise HTTPException(status_code=500, detail="KITE_API_KEY or KITE_API_SECRET not configured.")
    try:
        kite = KiteConnect(api_key=settings.KITE_API_KEY)
        session_data = kite.generate_session(request_token, api_secret=settings.KITE_API_SECRET)
        access_token = session_data["access_token"]
        kite.set_access_token(access_token)
        profile = kite.profile()
        settings.set_access_token(access_token)
        return {
            "authenticated": True,
            "message": f"Authenticated as {profile.get('user_name')} ({profile.get('user_id')})",
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token exchange failed: {e}")


@router.post("/postback")
async def kite_postback(request: dict):
    """
    Zerodha pushes order/trade status updates here in real-time.

    Postback URL to register in Kite developer console:
      https://genre-huskiness-twentieth.ngrok-free.dev/api/auth/postback

    Zerodha sends this payload when an order is:
      - placed, modified, cancelled, executed, rejected

    We use it to keep trading_service positions in sync without polling.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[KITE POSTBACK] {request}")

    order_id  = request.get("order_id", "")
    status    = request.get("status", "")        # COMPLETE, REJECTED, CANCELLED
    symbol    = request.get("tradingsymbol", "")
    avg_price = request.get("average_price", 0.0)
    tx_type   = request.get("transaction_type", "")  # BUY / SELL

    if status == "COMPLETE" and symbol and avg_price:
        from services import trading_service
        state = trading_service.get_state()

        # If this is an exit order (SELL on a LONG position we're tracking)
        if tx_type == "SELL" and symbol in state.positions:
            pos = state.positions[symbol]
            pnl_pct = pos.current_pnl_pct(float(avg_price))
            logger.info(
                f"[KITE POSTBACK] Exit confirmed: {symbol} @ ₹{avg_price} "
                f"| P&L: {pnl_pct:.2f}%"
            )

    elif status == "REJECTED":
        import logging as _log
        _log.getLogger(__name__).warning(
            f"[KITE POSTBACK] Order REJECTED: {symbol} | reason: {request.get('status_message', '')}"
        )

    return {"status": "received", "order_id": order_id}


# ═════════════════════════════════════════════════════════════════
#  Fyers auth  (OAuth2 code flow)
#
#  Flow:
#   1. GET  /api/auth/fyers/login-url   → open URL in browser
#   2. User logs in → Fyers redirects to FYERS_REDIRECT_URL?auth_code=XXX
#   3. GET  /api/auth/fyers/callback    → auto-exchanges code for token
#   4. Done — token stored in memory, bot can now trade via Fyers
# ═════════════════════════════════════════════════════════════════

def _fyers_session():
    try:
        from fyers_apiv3 import fyersModel
    except ImportError:
        raise HTTPException(status_code=500, detail="fyers-apiv3 not installed.")
    if not settings.FYERS_APP_ID or not settings.FYERS_SECRET:
        raise HTTPException(status_code=500, detail="FYERS_APP_ID / FYERS_SECRET not configured. Check .env.")
    return fyersModel.SessionModel(
        client_id=settings.FYERS_APP_ID,
        secret_key=settings.FYERS_SECRET,
        redirect_uri=settings.FYERS_REDIRECT_URL,
        response_type="code",
        grant_type="authorization_code",
    )


@router.get("/fyers/status")
def fyers_status():
    return {
        "authenticated": settings.is_fyers_authenticated(),
        "message": "Fyers token active" if settings.is_fyers_authenticated() else "Not authenticated with Fyers",
    }


@router.get("/fyers/login-url")
def fyers_login_url():
    """
    Step 1: Call this to get the Fyers login URL.
    Open that URL in your browser → log in → you'll be redirected back
    to http://127.0.0.1:8000/api/auth/fyers/callback automatically.
    """
    session = _fyers_session()
    url = session.generate_authcode()
    return {
        "login_url": url,
        "instructions": (
            "Open the login_url in your browser. "
            "After login, Fyers will redirect you to your callback URL automatically. "
            "The access token will be set without any manual steps."
        ),
    }


@router.get("/fyers/callback", response_class=HTMLResponse)
def fyers_callback(auth_code: str = Query(...), state: str = Query(default="")):
    """
    Step 2 (auto): Fyers redirects here after login with ?auth_code=XXX
    Exchanges the code for an access token and stores it in memory.
    """
    session = _fyers_session()
    try:
        session.set_token(auth_code)
        response = session.generate_token()
    except Exception as e:
        return HTMLResponse(content=_html_page("error", f"Token exchange failed: {e}"), status_code=500)

    if response.get("s") != "ok":
        msg = response.get("message", str(response))
        return HTMLResponse(content=_html_page("error", f"Fyers error: {msg}"), status_code=401)

    access_token = response.get("access_token", "")
    if not access_token:
        return HTMLResponse(content=_html_page("error", "No access_token in Fyers response."), status_code=500)

    settings.set_fyers_token(access_token)
    return HTMLResponse(content=_html_page("success", "Fyers authenticated successfully! You can close this tab."))


@router.post("/fyers/token")
def fyers_set_token_manual(body: TokenRequest):
    """
    Alternative: paste a Fyers access token manually (e.g. if callback fails).
    Useful when running behind a non-public IP during early dev.
    """
    token = body.access_token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token cannot be empty.")
    try:
        from fyers_apiv3 import fyersModel
        fyers = fyersModel.FyersModel(
            client_id=settings.FYERS_APP_ID,
            is_async=False,
            token=token,
            log_path="",
        )
        profile = fyers.get_profile()
        if profile.get("s") != "ok":
            raise ValueError(profile.get("message", "Invalid token"))
        settings.set_fyers_token(token)
        name = profile.get("data", {}).get("name", "User")
        return {"authenticated": True, "message": f"Fyers authenticated as {name}"}
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Fyers token: {e}")


@router.delete("/fyers/token")
def fyers_clear_token():
    settings.set_fyers_token("")
    return {"authenticated": False, "message": "Fyers token cleared."}


# ═════════════════════════════════════════════════════════════════
#  Fyers postback (order/trade notifications webhook)
# ═════════════════════════════════════════════════════════════════

@router.post("/fyers/postback")
def fyers_postback(payload: dict):
    """
    Fyers sends order update webhooks here.
    Postback URL to set in Fyers developer console:
      Local : http://127.0.0.1:8000/api/auth/fyers/postback
      AWS   : https://your-domain.com/api/auth/fyers/postback
    """
    import logging
    logging.getLogger(__name__).info(f"Fyers postback: {payload}")
    # Future: parse and sync order status with trading_service
    return {"status": "received"}


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _html_page(status: str, message: str) -> str:
    color = "#22c55e" if status == "success" else "#ef4444"
    icon = "✅" if status == "success" else "❌"
    return f"""<!DOCTYPE html>
<html><head><title>Fyers Auth</title>
<style>
  body{{font-family:Arial,sans-serif;display:flex;align-items:center;
       justify-content:center;height:100vh;margin:0;background:#0f172a;}}
  .card{{background:#1e293b;color:#e2e8f0;padding:40px;border-radius:12px;
         text-align:center;max-width:400px;box-shadow:0 4px 24px rgba(0,0,0,.4);}}
  h2{{color:{color};margin-top:0;}}
</style></head>
<body><div class="card">
  <h2>{icon} {status.upper()}</h2>
  <p>{message}</p>
  <p style="color:#64748b;font-size:13px;margin-top:24px;">
    Stock Analyser &mdash; Fyers Auth
  </p>
</div></body></html>"""
