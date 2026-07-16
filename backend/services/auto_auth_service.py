"""
Automated Zerodha daily login using credentials + TOTP.

Zerodha tokens expire at midnight every day. This service automates
the login at 8:30 AM so Jarvis is ready before market open at 9:00 AM.

Required credentials in .env / Parameter Store:
  ZERODHA_USER_ID      - your Zerodha client ID (e.g. AB1234)
  ZERODHA_PASSWORD     - your Zerodha login password
  ZERODHA_TOTP_SECRET  - base32 secret from your TOTP setup (see README)
"""

import logging
from urllib.parse import urlparse, parse_qs

import httpx
import pyotp
from kiteconnect import KiteConnect

from config import settings

logger = logging.getLogger(__name__)

_KITE_BASE = "https://kite.zerodha.com"


async def auto_login_zerodha() -> tuple[bool, str]:
    """
    Automates the full Zerodha login flow:
      1. POST /api/login        (user + password)
      2. POST /api/twofa        (TOTP code)
      3. GET  Kite login URL    (captures request_token from redirect)
      4. Exchange request_token → access_token via KiteConnect

    Returns (success: bool, message: str)
    """
    missing = [
        f for f in ["ZERODHA_USER_ID", "ZERODHA_PASSWORD", "ZERODHA_TOTP_SECRET"]
        if not getattr(settings, f, "")
    ]
    if missing:
        msg = f"Auto-login skipped — missing: {', '.join(missing)}"
        logger.warning(msg)
        return False, msg

    if not settings.KITE_API_KEY or not settings.KITE_API_SECRET:
        return False, "KITE_API_KEY or KITE_API_SECRET not configured"

    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=30) as client:

            # ── Step 1: Username + password login ───────────────────────────
            r1 = await client.post(
                f"{_KITE_BASE}/api/login",
                data={"user_id": settings.ZERODHA_USER_ID, "password": settings.ZERODHA_PASSWORD},
            )
            data1 = r1.json()
            if data1.get("status") != "success":
                msg = f"Login failed: {data1.get('message', 'unknown error')}"
                logger.error(f"[AUTO-AUTH] {msg}")
                return False, msg

            request_id = data1["data"]["request_id"]
            logger.info(f"[AUTO-AUTH] Step 1 OK — request_id: {request_id}")

            # ── Step 2: TOTP verification ────────────────────────────────────
            totp_code = pyotp.TOTP(settings.ZERODHA_TOTP_SECRET).now()
            r2 = await client.post(
                f"{_KITE_BASE}/api/twofa",
                data={
                    "user_id":     settings.ZERODHA_USER_ID,
                    "request_id":  request_id,
                    "twofa_value": totp_code,
                    "twofa_type":  "totp",
                },
            )
            data2 = r2.json()
            if data2.get("status") != "success":
                msg = f"2FA failed: {data2.get('message', 'unknown error')}"
                logger.error(f"[AUTO-AUTH] {msg}")
                return False, msg

            logger.info("[AUTO-AUTH] Step 2 OK — TOTP verified, session active")

            # ── Step 3: Hit the Kite Connect login URL to get request_token ─
            kite = KiteConnect(api_key=settings.KITE_API_KEY)
            connect_url = kite.login_url()

            r3 = await client.get(connect_url)
            location = r3.headers.get("location", "")

            # Follow up to 5 redirects to find the one with request_token
            for _ in range(5):
                if "request_token" in location:
                    break
                if not location:
                    break
                r3 = await client.get(location)
                location = r3.headers.get("location", "")

            if "request_token" not in location:
                msg = f"request_token not found in redirect chain. Last location: {location}"
                logger.error(f"[AUTO-AUTH] {msg}")
                return False, msg

            params = parse_qs(urlparse(location).query)
            request_token = params["request_token"][0]
            logger.info(f"[AUTO-AUTH] Step 3 OK — got request_token")

            # ── Step 4: Exchange request_token → access_token ────────────────
            session = kite.generate_session(request_token, api_secret=settings.KITE_API_SECRET)
            settings.set_access_token(session["access_token"])

            name = session.get("user_name", "User")
            msg = f"Zerodha auto-login successful — authenticated as {name}"
            logger.info(f"[AUTO-AUTH] {msg}")
            return True, msg

    except Exception as e:
        msg = f"Auto-login error: {e}"
        logger.error(f"[AUTO-AUTH] {msg}")
        return False, msg


def auto_login_zerodha_sync() -> tuple[bool, str]:
    """Synchronous wrapper — used by APScheduler (which runs in threads)."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(auto_login_zerodha())
    except RuntimeError:
        return asyncio.run(auto_login_zerodha())
