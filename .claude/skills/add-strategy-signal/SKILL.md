---
name: add-strategy-signal
description: This skill should be used when the user asks to "add a new indicator", "add a new strategy", "add a scoring factor", "enrich the screener", "add a new signal to the scanner", or wants to extend the composite buy/sell scoring in screener_service.py with a new technical, fundamental, or pattern-based factor.
version: 0.1.0
---

# Add a new strategy/signal to the screener

Jarvis's composite `signal_score` (0-100) is the sum of 9 independent sub-scores, each computed by a small pure function in `backend/services/screener_service.py` and summed in `scan_symbol()`. Adding a new enrichment means adding a 10th (or replacing/rebalancing an existing) sub-score — never bypass this scoring path with a separate decision mechanism, or the frontend/AI narrative/risk-suggestion logic that all key off `signal_score` and `signal` will silently disagree with the new factor.

Read `docs/TRADING_LOGIC.md` §1 first for the current weight table before changing anything — it must be kept in sync with this code.

## Procedure

1. **Compute the raw signal in its own service module.** If the data doesn't already exist (e.g. a new external data source, a new pattern detector), create `backend/services/<name>_service.py` following the existing modules' shape: pure functions taking a `pd.DataFrame` of OHLCV candles (or symbol string) in, returning plain dicts/floats out, no I/O side effects beyond the fetch itself. Look at `technical_service.py` or `trendline_service.py` as the shortest reference implementations.

2. **Add a scorer function to `screener_service.py`.** Follow the exact pattern of the existing `_xxx_score()` functions (e.g. `_macd_score`, `_rsi_score`, `screener_service.py:42-164`): take the relevant indicator dict/value, return an `int` between 0 and roughly 10-15. The 9 existing factors currently sum to a max of **130**, not the "0-100" the module docstring claims (check the current table in `docs/TRADING_LOGIC.md` §1) — adding another unscaled factor pushes the real ceiling higher still and shifts what fraction of "full marks" the STRONG BUY/BUY/WATCH/NEUTRAL thresholds (75/60/45) actually represent. Either:
   - Rebalance: reduce 1-2 existing factors' max points to keep the ceiling roughly where it was, or
   - Deliberately accept the new ceiling and note the change (and the new effective ceiling) in `docs/TRADING_LOGIC.md` — don't leave the doc silently wrong.

3. **Wire it into `scan_symbol()`** (`screener_service.py:167`):
   - Call the new service function alongside the existing `indicators`/`patterns`/`waves`/etc. calls, each already wrapped in its own `try/except` that logs a warning and degrades to an empty/neutral value on failure — match that resilience pattern, a new data source failing must never crash the whole scan.
   - Add the new key to the `scores = {...}` dict (`screener_service.py:235`).
   - If the new signal should be visible to the frontend or the Claude narrative, also add it to `result[...]`.

4. **If the signal should affect stop-loss/target/trade_type**, extend the `if signal in ("BUY", "STRONG BUY")` block (`screener_service.py:263-296`) — this is a separate decision from the score. Do not touch `trading_service.py` for this; sizing/risk gates are downstream and orthogonal to signal generation (see `docs/TRADING_LOGIC.md` §2).

5. **Verify before calling it done:**
   ```bash
   cd backend && python3 -m py_compile services/<name>_service.py services/screener_service.py
   ```
   Then start the backend (`uvicorn main:app --reload --port 8000`) and hit `GET /api/scanner/symbol/{symbol}` (with `X-API-Key`) for a real, liquid symbol (e.g. RELIANCE, TCS). Confirm:
   - `signal_score` stays within 0-100
   - `score_breakdown` shows the new key with a sane value
   - The overall `signal` classification didn't unexpectedly flip for symbols you know the prior behavior of

6. **Update `docs/TRADING_LOGIC.md` §1's weight table in the same change** — it is the source of truth future sessions (and future you) will trust instead of re-reading this file.

## Common mistake to avoid

Don't add a new "auto-trade this signal" path in `scheduler_service.py` as part of adding a scoring factor — auto-trading is gated centrally through `signal == "STRONG BUY"` in `job_intraday_scan` (`scheduler_service.py:139-159`). A new factor should influence the score, not create a second, parallel auto-trade trigger.
