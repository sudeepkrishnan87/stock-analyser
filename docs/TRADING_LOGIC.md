# Trading logic — how Jarvis actually decides to trade

This is a reverse-engineered map of the real decision path, with file:line references, current as of the codebase on 2026-07-16. If you change the scoring/risk code, update this doc in the same PR — it's the thing future-you (or Claude) will trust instead of re-reading five files.

## 1. Signal generation — `services/screener_service.py`

For any symbol, `scan_symbol()` (`screener_service.py:167`) builds a composite `signal_score` from 9 independent sub-scores, each computed from a separate service module and summed (`screener_service.py:235-246`). **Note**: the module docstring calls this a "0-100" score, but the nine factor maximums actually sum to **130** (15×8 + 10 for MACD) — this is a real discrepancy in the code, not a documentation error here. It doesn't break anything (the STRONG BUY/BUY/WATCH thresholds below are just thresholds against whatever the sum produces), but don't assume 100 is the ceiling when reasoning about "how close to maxed out" a score is, and don't silently "fix" it to sum to 100 without checking whether recalibrating the 75/60/45 thresholds is intended — that would change every historical STRONG BUY/BUY classification's meaning.

| Factor | Function | Max pts | What earns full marks |
|---|---|---|---|
| Volume spike | `_volume_score` | 15 | volume_ratio ≥ 3.0x average |
| RSI zone | `_rsi_score` | 15 | RSI 45-65 (trending, not overbought) |
| Bollinger position | `_bollinger_score` | 15 | price at/near lower band (mean-reversion buy zone) |
| Candlestick pattern | `_candlestick_score` | 15 | 2 bullish patterns (Hammer, Morning Star, etc.) in last 6 candles |
| MACD | `_macd_score` | 10 | MACD > signal line AND histogram positive |
| SMA trend | `_sma_trend_score` | 15 | price above SMA20/50/200 + golden cross (SMA50 > SMA200) |
| Elliott Wave | `_elliott_score` | 15 | end of Wave 2 (Wave 3 starting) — the single highest-weighted individual condition |
| Trendline breakout | `_trendline_score` | 15 | confirmed breakout with volume; breakdowns score 0 (bearish, irrelevant to a BUY screen) |
| Fundamentals | `_fundamental_score_contribution` | 15 | yfinance-derived fundamental_score ≥ 75; unknown/unavailable fundamentals default to a neutral 5, not 0 |

**Classification** (`screener_service.py:251-258`):
```
score >= 75  → STRONG BUY   (the only signal the scheduler will auto-trade)
score >= 60  → BUY
score >= 45  → WATCH
else         → NEUTRAL
```

**Trade suggestion** (only computed for BUY/STRONG BUY, `screener_service.py:263-296`):
- Stop-loss = `max(entry * 0.97, nearest_support * 0.995)` — whichever is *tighter is not chosen*; it takes the max, i.e. the wider of the two floors, biasing toward the support level when one exists below price.
- Target = `min(entry * 1.08, nearest_resistance * 0.998)`.
- Trade is only surfaced if **R:R ≥ 1.5**; otherwise no `trade_suggestion` is attached even though the signal itself is BUY/STRONG BUY.
- `trade_type` = INTRADAY if RSI > 68, else SWING — this is the only place trade_type is decided, and it's a side-effect of RSI, not of which scan (premarket/intraday/swing) triggered it.

There is no ML model anywhere in this path — every number above is a deterministic rule. `services/claude_service.py` runs *after* this and only produces a narrative explanation; its output (`signal/confidence/target/stop_loss/risks`) is shown in the frontend's AI panel but never fed back into `screener_service` or `trading_service`. If Claude's API key is missing or the call errors, it silently falls back to a canned "HOLD/LOW confidence" object (`claude_service.py:164-167`) — a bad model id or auth failure will not surface as an error to you, just a bland fallback.

## 2. Risk management — `services/trading_service.py` + `config.py`

Four env-driven gates, all defined in `config.py:76-81`:

| Env var | Default | Enforced where |
|---|---|---|
| `TRADING_CAPITAL` | ₹100,000 | base for all % calculations |
| `MAX_RISK_PER_TRADE_PCT` | 2% | `calculate_position_size()` (`trading_service.py:213`) |
| `MAX_PORTFOLIO_EXPOSURE_PCT` | 60% | caps position size in the same function, *and* re-checked as a hard gate in `can_enter_trade()` |
| `DAILY_LOSS_LIMIT_PCT` | 3% | `can_enter_trade()` (`trading_service.py:234`) |
| `MAX_OPEN_POSITIONS` | 5 | `can_enter_trade()` |

**Position sizing** (`trading_service.py:213-231`):
```
risk_amount   = capital * (MAX_RISK_PER_TRADE_PCT / 100)
shares        = risk_amount / abs(entry - stop_loss)
max_deployable = capital * (MAX_PORTFOLIO_EXPOSURE_PCT / 100) - already_deployed_capital
shares        = min(shares, max_deployable / entry)
```

**Important limitation**: all four gates are checked **only at trade-entry time** (`can_enter_trade()`, called from `enter_trade()`). They are not re-evaluated continuously. `monitor_positions()` (`trading_service.py:402`, called every 15 min by the scheduler) checks each open position's own SL/target/trailing stop, but does **not** re-check `DAILY_LOSS_LIMIT_PCT` as a circuit breaker mid-day — if unrealized losses on open positions deepen between scheduler ticks, nothing forces an exit until either that position's own SL is hit or someone tries to open a *new* trade (which is when the daily-loss gate would then block further entries).

**Trailing stop** (`monitor_positions()`, `trading_service.py:421-439`): activates once a position is +5%, trails 3% below the running peak (LONG) or above the running trough (SHORT); it only ever tightens in the favorable direction, never loosens.

**Entry-time additional gate** (`routers/trading.py:92-100`, mirrored inside `enter_trade()` at `trading_service.py:270`): R:R must be ≥ 1.5 or the order is rejected before it ever reaches the broker.

State (`Position`, `ClosedTrade` dataclasses) lives in a module-level singleton, persisted to `backend/data/trades.json` after every mutation (`trading_service.py:322, 384, 448`) and reloaded on process start. There is no database and no integrity check on that file — a manually edited or corrupted JSON silently becomes "reality" for open positions on next load.

## 3. Automation timeline — `services/scheduler_service.py` (IST, Mon–Fri)

| Time | Job | What it does |
|---|---|---|
| 08:30 | `job_auto_login` | Scripted Zerodha web-login via stored password + live TOTP code (see `docs/SECURITY.md` §Zerodha auto-login) |
| 09:00 | `job_premarket_scan` | Full watchlist + fundamentals, `min_score=60`, top 5 emailed **and** queued to `signal_service` for approval in the Signals tab, TTL until today's 15:15 close |
| 09:15–15:15, every 15 min | `job_intraday_scan` | 1) `monitor_positions()` first (SL/target/trailing checks on existing positions) 2) scans top 15 watchlist symbols on 15-min candles 3) **for the top 3 results, if `signal == STRONG BUY` AND there's a confirmed trendline breakout**, it alerts **and** queues to `signal_service` (`scheduler_service.py:144-166`), TTL 20 min — no order is ever placed automatically; entering the trade requires approving it in the Signals tab or a separate, human-initiated call to the trading API |
| 15:15 | `job_exit_intraday` | Square off all MIS/INTRADAY positions before close |
| 15:35 | `job_daily_report` | P&L summary via email/WhatsApp |
| 15:45 | `job_swing_scan` | EOD scan, `min_score=65`, top 3 emailed **and** queued to `signal_service` for next-day entry, TTL ~24h |

**No job in this file ever calls `enter_trade()` directly.** Every candidate any scan finds — premarket, intraday, or swing — goes through the same human-approval gate in the Signals tab (`services/signal_service.py`, `routers/signals.py`); only `approve_signal()` bridges into `trading_service.enter_trade()`, and that only runs when you click Approve. The three scan types differ only in *how long* a signal stays valid before expiring unapproved (20 min / until close / ~24h) and which `trade_type` (INTRADAY→MIS vs SWING→CNC) the resulting order uses.

## 4. Order execution — `brokers/zerodha.py` / `brokers/fyers.py`

`trading_service.enter_trade()` → `_get_broker()` picks Zerodha or Fyers per `ACTIVE_BROKER` → `broker.place_order(order_type="MARKET")`. Both brokers place **live market orders directly**; there is no paper/simulation broker class. `dry_run=True` is a parameter on `enter_trade()` (surfaced via `POST /api/trading/dry-run`) that returns the computed sizing without calling the broker — it is not a global switch, so every other call path (including the scheduler's auto-entry) is live by default.

Order lifecycle sync happens via broker webhooks: Zerodha → `POST /api/auth/postback`, Fyers → `POST /api/auth/fyers/postback`. Both are public (unauthenticated by API key, since brokers can't send it) — the Zerodha handler now verifies Zerodha's HMAC checksum before trusting the payload (fixed — see `docs/SECURITY.md`); the Fyers handler is still a stub that only logs (`routers/auth.py:326-337`, literally commented "Future: parse and sync"). Neither postback reconciles `trading_service`'s in-memory state beyond a P&L log line — the source of truth for "am I in a position" remains `trades.json`, updated only by the code paths in `trading_service.py` itself, not by broker callbacks.

## 5. Zerodha auth — two distinct flows, different risk profiles

1. **Official OAuth** (`routers/auth.py:32-163`): `/login-url` → browser login → Zerodha redirects to `/api/auth/callback?request_token=...` (public path) → `KiteConnect.generate_session()` exchanges it for an access token. Standard, documented, revocable.
2. **Scripted auto-login** (`services/auto_auth_service.py`): POSTs your stored `ZERODHA_USER_ID`/`ZERODHA_PASSWORD` to `kite.zerodha.com/api/login`, then a TOTP code computed live from the stored `ZERODHA_TOTP_SECRET` (raw base32 seed, via `pyotp`) to `/api/twofa`, then follows Kite Connect's `login_url()` under that now-authenticated web session to capture `request_token`, then completes the same `generate_session` exchange. This automates against Zerodha's **internal, undocumented web endpoints**, not the Kite Connect API — see `docs/SECURITY.md` for why storing the TOTP seed is materially riskier than storing a password alone (the seed lets anyone with it generate valid 2FA codes indefinitely, i.e., it *is* your second factor, not a credential protected by one).

Access tokens for both brokers live only in `Settings._kite_access_token` / `_fyers_access_token` — class-level, in-memory, gone on every process restart. That's why both the startup task (`main.py:41-53`) and the 08:30 job exist — Fyers has no equivalent auto-refresh, so a Fyers session lost to a restart requires manual re-auth.

## 6. Where the frontend actually reaches

The React SPA (`frontend/src`) has two tabs: **Research** (`GET /api/stock/{symbol}` — chart + indicators + candlestick patterns + FII/DII + AI narrative) and **Signals** (`GET/POST /api/signals/*` — the pending-approval queue described in §3, with Approve/Reject actions and a live favicon/tab-title badge). The broader scanner and trading endpoints (`/api/scanner/*`, most of `/api/trading/*`) are still called nowhere in the frontend beyond that — they exist in `api/client.ts` but have no dedicated page. Full picture in `docs/ARCHITECTURE.md`.
