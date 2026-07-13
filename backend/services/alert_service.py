"""
Alert service: sends Email (SMTP) and WhatsApp (Twilio) notifications.

Email uses smtplib with TLS — works with Gmail App Passwords.
WhatsApp uses Twilio's WhatsApp Business sandbox.

Setup for Gmail:
  1. Enable 2-FA on your Google account.
  2. Create an App Password at myaccount.google.com/apppasswords.
  3. Set EMAIL_SENDER and EMAIL_PASSWORD in .env.

Setup for WhatsApp (Twilio sandbox):
  1. Sign up at twilio.com, go to Messaging > Try it Out > Send a WhatsApp message.
  2. From your phone, send the join code to the Twilio sandbox number.
  3. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM, TWILIO_WHATSAPP_TO in .env.
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, List, Optional

import pytz

from config import settings

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


# ── In-memory alert history (last 200 alerts) ─────────────────────────────────
_alert_history: List[Dict] = []


def _now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")


# ─────────────────────────────────────────────────────────────────────────────
# Email
# ─────────────────────────────────────────────────────────────────────────────

def _build_email_html(subject: str, body: str) -> str:
    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
    <div style="background:#1a1a2e;color:#eee;padding:20px;border-radius:8px;">
      <h2 style="color:#f0c040;margin-top:0;">📈 Stock Alert — {_now_ist()}</h2>
      <h3 style="color:#fff;border-bottom:1px solid #444;padding-bottom:8px;">{subject}</h3>
      <div style="background:#16213e;padding:15px;border-radius:6px;white-space:pre-wrap;
                  font-family:monospace;font-size:14px;line-height:1.6;">{body}</div>
      <p style="color:#888;font-size:12px;margin-top:20px;">
        Sent by Stock Analyser AI | Trade at your own risk.
      </p>
    </div></body></html>
    """


def send_email(subject: str, body: str) -> bool:
    if not all([settings.EMAIL_SENDER, settings.EMAIL_PASSWORD, settings.EMAIL_RECIPIENT]):
        logger.warning("Email credentials not configured. Skipping email alert.")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[StockBot] {subject}"
        msg["From"] = settings.EMAIL_SENDER
        msg["To"] = settings.EMAIL_RECIPIENT
        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(_build_email_html(subject, body), "html"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(settings.EMAIL_SENDER, settings.EMAIL_PASSWORD)
            smtp.sendmail(settings.EMAIL_SENDER, settings.EMAIL_RECIPIENT, msg.as_string())
        logger.info(f"Email alert sent: {subject}")
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# WhatsApp (Twilio)
# ─────────────────────────────────────────────────────────────────────────────

def send_whatsapp(message: str) -> bool:
    if not all([settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_WHATSAPP_TO]):
        logger.warning("Twilio credentials not configured. Skipping WhatsApp alert.")
        return False
    try:
        from twilio.rest import Client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=message,
            from_=settings.TWILIO_WHATSAPP_FROM,
            to=settings.TWILIO_WHATSAPP_TO,
        )
        logger.info("WhatsApp alert sent.")
        return True
    except ImportError:
        logger.error("twilio package not installed. Run: pip install twilio")
        return False
    except Exception as e:
        logger.error(f"WhatsApp send failed: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Unified alert dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def send_alert(subject: str, body: str, via_email: bool = True, via_whatsapp: bool = True) -> Dict:
    """Send alert via configured channels. Returns status dict."""
    _alert_history.append({
        "timestamp": _now_ist(),
        "subject": subject,
        "body": body,
    })
    if len(_alert_history) > 200:
        _alert_history.pop(0)

    results = {}
    if via_email:
        results["email"] = send_email(subject, body)
    if via_whatsapp:
        wa_msg = f"*{subject}*\n\n{body}\n\n_{_now_ist()}_"
        results["whatsapp"] = send_whatsapp(wa_msg)
    return results


def get_alert_history() -> List[Dict]:
    return list(reversed(_alert_history))


# ─────────────────────────────────────────────────────────────────────────────
# Pre-built alert formatters
# ─────────────────────────────────────────────────────────────────────────────

def alert_breakout(symbol: str, signal: Dict, fundamentals: Optional[Dict] = None) -> Dict:
    sig_type = signal.get("signal_type", "SIGNAL")
    direction = signal.get("direction", "")
    emoji = "🚀" if direction == "BULLISH" else "📉"

    lines = [
        f"{emoji} {sig_type} — {symbol}",
        f"{'─' * 40}",
        f"Price       : ₹{signal.get('current_price', 0):.2f}",
        f"Trendline   : ₹{signal.get('trendline_value', 0):.2f}",
        f"Break %     : {signal.get('breakout_pct', 0):.2f}%",
        f"Volume      : {signal.get('volume_ratio', 0):.1f}x average  ✅" if signal.get("volume_confirmed") else f"Volume      : {signal.get('volume_ratio', 0):.1f}x average",
        f"",
        f"Entry       : ₹{signal.get('suggested_entry', 0):.2f}",
        f"Stop Loss   : ₹{signal.get('suggested_sl', 0):.2f}",
        f"Target      : ₹{signal.get('suggested_target', 0):.2f}",
        f"R:R Ratio   : 1:{signal.get('rr_ratio', 0):.1f}",
    ]

    if fundamentals:
        lines += [
            f"",
            f"── Fundamentals ──",
            f"PE Ratio    : {fundamentals.get('pe_ratio', 'N/A')}",
            f"EBITDA Mgn  : {fundamentals.get('ebitda_margin_pct', 'N/A')}%",
            f"Fund Score  : {fundamentals.get('fundamental_score', 'N/A')}/100 ({fundamentals.get('fundamental_grade', 'N/A')})",
        ]

    body = "\n".join(lines)
    return send_alert(f"{emoji} {sig_type}: {symbol}", body)


def alert_trade_executed(symbol: str, action: str, quantity: int, price: float, order_id: str) -> Dict:
    emoji = "✅" if action == "BUY" else "🔴"
    body = (
        f"{emoji} {action} ORDER EXECUTED\n"
        f"{'─' * 40}\n"
        f"Symbol   : {symbol}\n"
        f"Quantity : {quantity} shares\n"
        f"Price    : ₹{price:.2f}\n"
        f"Value    : ₹{quantity * price:,.2f}\n"
        f"Order ID : {order_id}\n"
    )
    return send_alert(f"{emoji} {action}: {symbol} @ ₹{price:.2f}", body)


def alert_stop_loss_hit(symbol: str, entry_price: float, sl_price: float, loss_pct: float) -> Dict:
    body = (
        f"🛑 STOP LOSS HIT — {symbol}\n"
        f"{'─' * 40}\n"
        f"Entry    : ₹{entry_price:.2f}\n"
        f"SL Hit   : ₹{sl_price:.2f}\n"
        f"Loss     : {loss_pct:.2f}%\n"
        f"\nPosition closed to protect capital."
    )
    return send_alert(f"🛑 SL HIT: {symbol} (-{loss_pct:.2f}%)", body)


def alert_target_hit(symbol: str, entry_price: float, target_price: float, gain_pct: float) -> Dict:
    body = (
        f"🎯 TARGET HIT — {symbol}\n"
        f"{'─' * 40}\n"
        f"Entry    : ₹{entry_price:.2f}\n"
        f"Target   : ₹{target_price:.2f}\n"
        f"Gain     : +{gain_pct:.2f}%\n"
        f"\nBooking profit. Excellent trade!"
    )
    return send_alert(f"🎯 TARGET: {symbol} (+{gain_pct:.2f}%)", body)


def alert_daily_report(report: Dict) -> Dict:
    pnl = report.get("daily_pnl", 0)
    emoji = "📈" if pnl >= 0 else "📉"
    body = (
        f"{emoji} DAILY TRADING REPORT\n"
        f"{'─' * 40}\n"
        f"Date         : {report.get('date', _now_ist())}\n"
        f"Capital      : ₹{report.get('capital', 0):,.2f}\n"
        f"Daily P&L    : ₹{pnl:+,.2f} ({report.get('daily_pnl_pct', 0):+.2f}%)\n"
        f"MTD P&L      : ₹{report.get('mtd_pnl', 0):+,.2f} ({report.get('mtd_pnl_pct', 0):+.2f}%)\n"
        f"QTD P&L      : ₹{report.get('qtd_pnl', 0):+,.2f} ({report.get('qtd_pnl_pct', 0):+.2f}%)\n"
        f"Open Pos.    : {report.get('open_positions', 0)}\n"
        f"Trades Today : {report.get('trades_today', 0)}\n"
        f"Win Rate     : {report.get('win_rate', 0):.1f}%\n"
    )
    return send_alert(f"{emoji} Daily Report | P&L: ₹{pnl:+,.2f}", body)
