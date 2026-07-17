"""
Background scheduler: runs automated scans and trading jobs during market hours.

Schedule (IST):
  09:00 AM  — Pre-market scan: top 5 picks, alert + queued for approval (Signals tab)
  09:15 AM  — Market open: first intraday scan
  Every 15m  — Intraday scan: top 3 STRONG BUY+breakout, alert + queued for approval;
              position monitor runs first (09:30 – 15:15)
  03:15 PM  — Exit all intraday positions
  03:35 PM  — Daily P&L report email + WhatsApp
  03:45 PM  — Swing scan: top 3 next-day setups, alert + queued for approval (~24h TTL)
  Weekdays only (Mon–Fri), no scan on NSE holidays.

No job in this file ever calls trading_service.enter_trade() — new entries always
require an explicit human-approved call to the trading API. Position monitoring/exit
of *already open* positions (SL, target, trailing stop, EOD square-off) still runs
unattended, since those only manage risk on trades a human already approved.

Uses APScheduler (BackgroundScheduler). Starts with the FastAPI app lifecycle.
"""

import logging
from datetime import datetime, time
from typing import Optional

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import settings

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

_scheduler: Optional[BackgroundScheduler] = None


def _minutes_until(hour: int, minute: int) -> int:
    """Minutes from now until today's given IST clock time (floor of 1 minute if already past)."""
    now = datetime.now(IST)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    delta = (target - now).total_seconds() / 60
    return max(1, int(delta))


# ─────────────────────────────────────────────────────────────────────────────
# Job functions
# ─────────────────────────────────────────────────────────────────────────────

def _get_active_broker():
    """Return the active broker instance if authenticated."""
    try:
        if settings.ACTIVE_BROKER.lower() == "fyers":
            from brokers.fyers import FyersBroker
            b = FyersBroker()
        else:
            from brokers.zerodha import ZerodhaBroker
            b = ZerodhaBroker()
        if not b.is_authenticated():
            return None
        return b
    except Exception as e:
        logger.warning(f"Could not get broker: {e}")
        return None


def job_auto_login():
    """8:30 AM — Auto-login to Zerodha so token is ready before market open."""
    logger.info("[SCHEDULER] Running automated Zerodha login...")
    from services.auto_auth_service import auto_login_zerodha_sync
    from services import alert_service
    success, message = auto_login_zerodha_sync()
    if success:
        logger.info(f"[SCHEDULER] {message}")
    else:
        logger.error(f"[SCHEDULER] Auto-login failed: {message}")
        alert_service.send_alert(
            "⚠️ Jarvis: Zerodha Login Failed",
            f"Auto-login at 8:30 AM failed.\nReason: {message}\n\nManual auth needed: /api/auth/login-url",
            via_email=True, via_whatsapp=False,
        )


def job_premarket_scan():
    """09:00 AM — Fetch overnight data, screen fundamentals, build watchlist."""
    logger.info("[SCHEDULER] Pre-market scan starting...")
    broker = _get_active_broker()
    if not broker:
        logger.warning("[SCHEDULER] Pre-market: broker not authenticated, skipping.")
        return

    from services import screener_service, alert_service, signal_service

    try:
        results = screener_service.scan_watchlist(
            settings.DEFAULT_WATCHLIST,
            broker=broker,
            include_fundamentals=True,
            min_score=60,
        )
        if results:
            top = results[:5]
            lines = ["PRE-MARKET WATCHLIST — Top Picks Today", "=" * 40]
            # Valid for approval through today's market close — these are same-day picks.
            ttl = _minutes_until(15, 15)
            for i, r in enumerate(top, 1):
                lines.append(
                    f"{i}. {r['symbol']} | Score: {r['signal_score']}/100 | "
                    f"Signal: {r['signal']} | ₹{r.get('current_price', 0):.2f}"
                )
                if r.get("trade_suggestion"):
                    ts = r["trade_suggestion"]
                    lines.append(
                        f"   Entry: ₹{ts['entry']} | SL: ₹{ts['stop_loss']} | "
                        f"Target: ₹{ts['target']} | R:R 1:{ts['rr_ratio']}"
                    )
                    signal_service.add_pending_signal(
                        symbol=r["symbol"],
                        signal=r["signal"],
                        signal_score=r.get("signal_score", 0),
                        trade_suggestion=ts,
                        source="PREMARKET",
                        breakout_signal=r.get("breakout_signal"),
                        ttl_minutes=ttl,
                    )
            body = "\n".join(lines)
            alert_service.send_alert("Pre-Market Top Picks", body)
            logger.info(f"[SCHEDULER] Pre-market scan found {len(results)} candidates.")
        else:
            logger.info("[SCHEDULER] Pre-market scan: no high-confidence picks today.")
    except Exception as e:
        logger.error(f"[SCHEDULER] Pre-market scan error: {e}")


def job_intraday_scan():
    """Every 15 minutes 09:30–15:15 — Scan for intraday breakouts + monitor positions."""
    now = datetime.now(IST)
    logger.info(f"[SCHEDULER] Intraday scan at {now.strftime('%H:%M')} IST")

    broker = _get_active_broker()
    if not broker:
        return

    from services import screener_service, trading_service, alert_service, signal_service

    # ── Monitor existing positions first ─────────────────────────────────────
    try:
        monitor_actions = trading_service.monitor_positions()
        for action in monitor_actions:
            if action.get("action") == "EXIT":
                logger.info(
                    f"[SCHEDULER] Position exited: {action['symbol']} — {action.get('reason')}"
                )
    except Exception as e:
        logger.error(f"[SCHEDULER] Position monitor error: {e}")

    # ── Scan for new intraday setups ─────────────────────────────────────────
    try:
        results = screener_service.scan_intraday(
            settings.DEFAULT_WATCHLIST[:15],   # scan top 15 for speed
            broker=broker,
            interval="15minute",
            days_back=30,
        )
        for r in results[:3]:   # alert on top 3
            if r.get("signal") in ("BUY", "STRONG BUY") and r.get("trade_suggestion"):
                # Alert + queue for approval — no trade is ever placed without explicit
                # human approval. See docs/SECURITY.md "no global paper-trading switch" finding.
                if r.get("breakout_signal") and r["signal"] == "STRONG BUY":
                    alert_service.alert_breakout(
                        r["symbol"], r["breakout_signal"],
                        fundamentals=r.get("fundamentals"),
                    )
                    signal_service.add_pending_signal(
                        symbol=r["symbol"],
                        signal=r["signal"],
                        signal_score=r.get("signal_score", 0),
                        trade_suggestion=r["trade_suggestion"],
                        source="INTRADAY",
                        breakout_signal=r.get("breakout_signal"),
                    )
    except Exception as e:
        logger.error(f"[SCHEDULER] Intraday scan error: {e}")


def job_exit_intraday():
    """3:15 PM — Square off all intraday positions before market close."""
    logger.info("[SCHEDULER] Squaring off all intraday positions...")
    from services import trading_service
    try:
        results = trading_service.exit_all_intraday()
        logger.info(f"[SCHEDULER] Exited {len(results)} intraday positions.")
    except Exception as e:
        logger.error(f"[SCHEDULER] EOD exit error: {e}")


def job_daily_report():
    """3:35 PM — Send daily P&L report."""
    logger.info("[SCHEDULER] Sending daily report...")
    from services import trading_service, alert_service
    try:
        summary = trading_service.portfolio_summary()
        history = trading_service.get_trade_history(limit=10)
        today_trades = [
            t for t in history
            if t["exit_time"].startswith(datetime.now(IST).strftime("%Y-%m-%d"))
        ]
        report = {
            "date": datetime.now(IST).strftime("%Y-%m-%d"),
            "capital": summary["capital"],
            "daily_pnl": summary["daily_pnl"],
            "daily_pnl_pct": summary["daily_pnl_pct"],
            "mtd_pnl": summary["mtd_pnl"],
            "mtd_pnl_pct": summary["mtd_pnl_pct"],
            "qtd_pnl": summary["qtd_pnl"],
            "qtd_pnl_pct": summary["qtd_pnl_pct"],
            "open_positions": summary["open_positions"],
            "trades_today": len(today_trades),
            "win_rate": summary["win_rate"],
        }
        alert_service.alert_daily_report(report)
    except Exception as e:
        logger.error(f"[SCHEDULER] Daily report error: {e}")


def job_swing_scan():
    """
    Daily at 3:45 PM — End-of-day swing trade setup scan.
    Looks for stocks forming setups for next-day entry.
    """
    logger.info("[SCHEDULER] End-of-day swing scan...")
    broker = _get_active_broker()
    if not broker:
        return

    from services import screener_service, alert_service, signal_service

    try:
        results = screener_service.scan_watchlist(
            settings.DEFAULT_WATCHLIST,
            broker=broker,
            include_fundamentals=False,
            min_score=65,
        )
        if results:
            top = results[:3]
            lines = ["SWING TRADE SETUPS FOR TOMORROW", "=" * 40]
            for i, r in enumerate(top, 1):
                ts = r.get("trade_suggestion", {})
                fund = r.get("fundamentals") or {}
                lines.append(
                    f"{i}. {r['symbol']} | {r['signal']} | Score: {r['signal_score']}/100"
                )
                if ts:
                    lines.append(
                        f"   Entry: ₹{ts.get('entry', 'N/A')} | "
                        f"SL: ₹{ts.get('stop_loss', 'N/A')} | "
                        f"Target: ₹{ts.get('target', 'N/A')} | "
                        f"R:R 1:{ts.get('rr_ratio', 'N/A')}"
                    )
                    # ~24h — meant for next trading day's entry, not today's. Approximate:
                    # doesn't account for weekends, so a Friday swing pick reads as
                    # "valid ~1 day" even though the next session is Monday.
                    signal_service.add_pending_signal(
                        symbol=r["symbol"],
                        signal=r["signal"],
                        signal_score=r.get("signal_score", 0),
                        trade_suggestion=ts,
                        source="SWING",
                        ttl_minutes=24 * 60,
                    )
                if fund.get("pe_ratio"):
                    lines.append(
                        f"   PE: {fund['pe_ratio']} | "
                        f"EBITDA Margin: {fund.get('ebitda_margin_pct', 'N/A')}% | "
                        f"Fund Grade: {fund.get('fundamental_grade', 'N/A')}"
                    )
                wave = r.get("waves", [])
                if wave:
                    lw = wave[-1]
                    lines.append(f"   Elliott: Wave {lw['wave_number']} ({lw['wave_type']})")
            alert_service.send_alert("Swing Setups for Tomorrow", "\n".join(lines))
    except Exception as e:
        logger.error(f"[SCHEDULER] Swing scan error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler lifecycle
# ─────────────────────────────────────────────────────────────────────────────

def start_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        logger.info("Scheduler already running.")
        return

    _scheduler = BackgroundScheduler(timezone=IST)

    # Auto-login at 8:30 AM (before market open)
    _scheduler.add_job(
        job_auto_login, CronTrigger(day_of_week="mon-fri", hour=8, minute=30, timezone=IST),
        id="auto_login", replace_existing=True,
    )

    # Pre-market (weekdays 9:00 AM IST)
    _scheduler.add_job(
        job_premarket_scan, CronTrigger(day_of_week="mon-fri", hour=9, minute=0, timezone=IST),
        id="premarket", replace_existing=True,
    )

    # Intraday scan every 15 minutes from 9:30 to 15:15 (weekdays)
    _scheduler.add_job(
        job_intraday_scan,
        CronTrigger(day_of_week="mon-fri", hour="9-15", minute="15,30,45,0", timezone=IST),
        id="intraday_scan", replace_existing=True,
    )

    # Square off intraday at 3:15 PM
    _scheduler.add_job(
        job_exit_intraday, CronTrigger(day_of_week="mon-fri", hour=15, minute=15, timezone=IST),
        id="exit_intraday", replace_existing=True,
    )

    # Daily report at 3:35 PM
    _scheduler.add_job(
        job_daily_report, CronTrigger(day_of_week="mon-fri", hour=15, minute=35, timezone=IST),
        id="daily_report", replace_existing=True,
    )

    # Swing scan at 3:45 PM
    _scheduler.add_job(
        job_swing_scan, CronTrigger(day_of_week="mon-fri", hour=15, minute=45, timezone=IST),
        id="swing_scan", replace_existing=True,
    )

    _scheduler.start()
    logger.info("Scheduler started. Jobs scheduled for market hours (IST, Mon-Fri).")


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")


def get_scheduler_status() -> dict:
    if not _scheduler:
        return {"running": False, "jobs": []}
    jobs = []
    for job in _scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id": job.id,
            "next_run": next_run.strftime("%Y-%m-%d %H:%M:%S IST") if next_run else "N/A",
        })
    return {"running": _scheduler.running, "jobs": jobs}


def trigger_scan_now(scan_type: str = "swing") -> str:
    """Manually trigger a scan job immediately."""
    if scan_type == "intraday":
        job_intraday_scan()
        return "Intraday scan triggered."
    elif scan_type == "premarket":
        job_premarket_scan()
        return "Pre-market scan triggered."
    elif scan_type == "swing":
        job_swing_scan()
        return "Swing scan triggered."
    return "Unknown scan type."
