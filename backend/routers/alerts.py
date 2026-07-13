"""
Alert management endpoints:
  GET  /api/alerts/history             — recent alert log
  POST /api/alerts/test/email          — send a test email
  POST /api/alerts/test/whatsapp       — send a test WhatsApp
  POST /api/alerts/test/both           — test both channels
  GET  /api/alerts/config              — show current alert config (redacted)
  POST /api/alerts/manual              — send a custom alert immediately
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from services import alert_service

router = APIRouter()


class ManualAlertRequest(BaseModel):
    subject: str
    body: str
    via_email: bool = True
    via_whatsapp: bool = True


@router.get("/history")
def alert_history(limit: int = 50):
    """Return the last N alerts that were dispatched."""
    history = alert_service.get_alert_history()
    return {"count": len(history), "alerts": history[:limit]}


@router.post("/test/email")
def test_email():
    """Send a test email to verify SMTP configuration."""
    ok = alert_service.send_email(
        subject="Test Alert — Stock Analyser",
        body=(
            "This is a test email from your Stock Analyser bot.\n\n"
            "If you received this, email alerts are configured correctly.\n"
            "You will receive trendline breakout/breakdown alerts here."
        ),
    )
    if not ok:
        raise HTTPException(
            status_code=500,
            detail="Email send failed. Check EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT in .env",
        )
    return {"status": "sent", "channel": "email"}


@router.post("/test/whatsapp")
def test_whatsapp():
    """Send a test WhatsApp message via Twilio."""
    ok = alert_service.send_whatsapp(
        "✅ *Test Alert — Stock Analyser*\n\n"
        "WhatsApp alerts are working correctly.\n"
        "You will receive breakout alerts here in real-time."
    )
    if not ok:
        raise HTTPException(
            status_code=500,
            detail=(
                "WhatsApp send failed. Check TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
                "TWILIO_WHATSAPP_FROM, TWILIO_WHATSAPP_TO in .env. "
                "Also ensure you have joined the Twilio sandbox by texting the join code."
            ),
        )
    return {"status": "sent", "channel": "whatsapp"}


@router.post("/test/both")
def test_both():
    """Send test alerts on all configured channels."""
    email_ok = alert_service.send_email(
        "Test Alert — Stock Analyser",
        "This is a test. Email alerts are working.",
    )
    wa_ok = alert_service.send_whatsapp(
        "✅ *Test Alert — Stock Analyser*\nWhatsApp alerts are working."
    )
    return {
        "email": "sent" if email_ok else "failed (check .env)",
        "whatsapp": "sent" if wa_ok else "failed (check .env)",
    }


@router.get("/config")
def alert_config():
    """Show current alert configuration (credentials redacted)."""
    from config import settings

    def _mask(s: str) -> str:
        if not s:
            return "NOT SET"
        if len(s) <= 4:
            return "****"
        return s[:2] + "****" + s[-2:]

    return {
        "email": {
            "sender": settings.EMAIL_SENDER or "NOT SET",
            "recipient": settings.EMAIL_RECIPIENT or "NOT SET",
            "smtp_host": settings.SMTP_HOST,
            "smtp_port": settings.SMTP_PORT,
            "password_set": bool(settings.EMAIL_PASSWORD),
        },
        "whatsapp": {
            "from": settings.TWILIO_WHATSAPP_FROM or "NOT SET",
            "to": settings.TWILIO_WHATSAPP_TO or "NOT SET",
            "account_sid": _mask(settings.TWILIO_ACCOUNT_SID),
            "auth_token_set": bool(settings.TWILIO_AUTH_TOKEN),
        },
    }


@router.post("/manual")
def send_manual_alert(req: ManualAlertRequest):
    """Send a custom alert immediately via selected channels."""
    if not req.subject.strip() or not req.body.strip():
        raise HTTPException(status_code=400, detail="subject and body are required")
    result = alert_service.send_alert(
        subject=req.subject,
        body=req.body,
        via_email=req.via_email,
        via_whatsapp=req.via_whatsapp,
    )
    return {"dispatched": result}
