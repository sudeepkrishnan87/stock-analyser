---
name: add-broker
description: This skill should be used when the user asks to "add a new broker", "integrate a new broker API", "add support for [broker name]", or wants to extend Jarvis beyond Zerodha/Fyers to another Indian broker (e.g. Upstox, AngelOne, Dhan).
version: 0.1.0
---

# Add a new broker integration

Jarvis's trading engine (`backend/services/trading_service.py`) is broker-agnostic by design — it only ever talks to the `BaseBroker` interface (`backend/brokers/base.py`), never to a broker SDK directly. Adding a broker means implementing that interface once; the screener, risk management, and scheduler all keep working unmodified.

## Procedure

1. **Read `backend/brokers/base.py` in full first.** It's short (under 75 lines). Every method is abstract except `ohlcv_to_candles()`, which is a shared default normalizer — reuse it unless the new broker's OHLCV shape genuinely doesn't fit `{date, open, high, low, close, volume}` dicts.

2. **Create `backend/brokers/<broker_name>.py`** implementing `BaseBroker`. Use `backend/brokers/zerodha.py` as the primary reference (it's the most complete/battle-tested) and `backend/brokers/fyers.py` as a second data point for how much symbol-format translation is typically needed (Fyers requires `NSE:XXX-EQ` instead of a plain symbol, for example — expect the new broker to have its own quirk here).

   Required methods and what callers expect from each:
   - `is_authenticated() -> bool` — checked before every scheduler job and most routes; must be cheap (no network call), just checks whether a token is present.
   - `get_instrument_token(symbol, exchange="NSE") -> (token_or_key, company_name)` — called before every historical/LTP fetch.
   - `fetch_historical(instrument_key, interval, days_back) -> List[Dict]` — `interval` values used elsewhere in this codebase are `"minute"`, `"15minute"`, `"day"`; if the broker's API doesn't support one of these natively (Zerodha has no native month interval — see `kite_service.py`'s manual daily→monthly resample as the precedent), resample rather than erroring.
   - `fetch_ltp(symbol, exchange="NSE") -> float`
   - `place_order(...) -> Optional[Dict]` — **must return a dict containing `order_id`** on success; `trading_service.enter_trade()` reads `order.get("order_id", "")` directly (`trading_service.py:318`) and silently stores an empty string if the key is missing, which breaks postback reconciliation later.
   - `cancel_order(order_id) -> bool`
   - `get_positions() -> List[Dict]`, `get_orders() -> List[Dict]`

3. **Add auth wiring in `routers/auth.py`** following the Fyers OAuth section (`routers/auth.py:211-337`) as the closer template if the new broker uses OAuth2 code flow, or the Zerodha section (`routers/auth.py:10-216`) if it uses Kite-style request-token exchange. Add the broker's access token storage to `config.py`'s `Settings` class (`set_<broker>_token`/`get_<broker>_token`/`is_<broker>_authenticated`, mirroring the existing `_kite_access_token`/`_fyers_access_token` pattern at `config.py:96-126`).

4. **If the broker sends order-status webhooks**, add a postback route — but do not skip signature verification the way the original Fyers postback stub did. Follow the pattern just added to the Zerodha postback (`routers/auth.py:189-197`): verify whatever HMAC/checksum scheme the broker documents *before* trusting the payload, since postback routes are necessarily public (unauthenticated by `X-API-Key`, since the broker can't send it) — see `docs/SECURITY.md`'s "unverified broker webhooks" finding for why this matters.

5. **Wire `ACTIVE_BROKER`**: `_get_broker()` in `trading_service.py:204` and `_get_active_broker()` in `scheduler_service.py:35` both branch on `settings.ACTIVE_BROKER.lower()` — add the new broker name as a third branch in both places (currently only `"fyers"` vs. default-Zerodha; changing this to an explicit if/elif/else for 3+ brokers is a reasonable small refactor to do at the same time).

6. **Verify:**
   ```bash
   cd backend && python3 -m py_compile brokers/<broker_name>.py routers/auth.py services/trading_service.py services/scheduler_service.py
   ```
   Then manually walk the OAuth flow against the broker's sandbox/dev environment if one exists, confirm `GET /api/auth/<broker>/status` flips to authenticated, and run `POST /api/trading/dry-run` (not a live order) against the new broker to confirm `calculate_position_size()` and the response shape work end to end before ever setting `ACTIVE_BROKER` to the new value in a real `.env`.

## Do not skip

Never set `ACTIVE_BROKER` to the new broker in production config until `place_order()` has been exercised against that broker's paper/sandbox mode (if it has one) or with a manual `/api/trading/dry-run` plus at least one manual real small-quantity order reviewed by hand. `trading_service.enter_trade()` has no broker-specific safety net — a broken `place_order()` implementation that returns a truthy-but-wrong dict will look like a successful trade to the risk engine.
