# Security audit — Jarvis

Threat model: **single operator, live trading money, public GitHub repo.** The two things that matter most are (1) nobody else can ever call the API, and (2) a leaked credential can't be used to silently drain or manipulate the account. Everything else is secondary.

Audited 2026-07-16 via full reverse-engineering pass. Status legend: 🔴 open · 🟡 accepted risk (documented, not fixed) · ✅ fixed.

## Findings

### 🔴 ~~Real API_SECRET_KEY committed to git~~ → ✅ fixed, rotation pending
`backend/.env.example` contained a real `secrets.token_urlsafe(32)`-shaped key (not a `your_x_here` placeholder) since the initial commit, in a **public** repo. Anyone with repo access has always had it.
- **Fixed in this pass**: `.env.example` now uses a placeholder.
- **You still need to do**: rotate the live key in AWS SSM + your local `.env` + browser localStorage. Exact commands were given separately in this session. Until you rotate, the old key is still valid in production.
- **Also worth doing eventually**: purge it from git history (`git filter-repo`) since it's a public repo — this rewrites history and breaks existing clones/forks, so only do it deliberately, not as a reflex.

### ✅ Fixed: non-constant-time API key comparison
`main.py` compared `api_key != expected` with plain string equality — theoretically vulnerable to a timing attack that leaks the key byte-by-byte. Now uses `hmac.compare_digest()`.

### ✅ Fixed: unverified broker order webhooks (Zerodha)
`/api/auth/postback` is necessarily public (Zerodha can't send your API key), but the handler trusted the JSON body with no signature check — anyone who found the URL could POST a fake `COMPLETE` order and have it logged as real P&L. Now verifies Zerodha's `checksum` field (`sha256(order_id + order_timestamp + api_secret)`) via `hmac.compare_digest` before touching any trading state.
- **Still open**: `/api/auth/fyers/postback` has no equivalent — Fyers' postback signing scheme wasn't verified in this pass (would need Fyers API docs in hand). Low urgency today since the handler is a no-op stub that only logs, but fix this **before** wiring it to update trading state.

### ✅ Fixed: CORS_ORIGINS hardcoded even in production
Was a fixed `localhost:5173/3000` list regardless of `ENVIRONMENT`. Dead/misleading config — didn't matter in the documented deploy (frontend + API are same-origin behind nginx) but would silently do the wrong thing if that topology ever changed. Now reads from `CORS_ORIGINS` env var (comma-separated), same default for local dev.

### 🟡 Accepted risk: Zerodha password + live TOTP seed stored server-side
`services/auto_auth_service.py` scripts a login against Zerodha's **internal, undocumented** web endpoints (`kite.zerodha.com/api/login`, `/api/twofa`) using the stored `ZERODHA_PASSWORD` and `ZERODHA_TOTP_SECRET` (the raw base32 seed — not a one-time code, the actual secret that generates valid codes forever). This is a stronger credential than the official Kite Connect OAuth flow requires: a leak of these two values gives permanent, self-service, 2FA-bypassing account access, and scripting a broker's web UI is fragile and ToS-adjacent.
- **Why accepted rather than fixed now**: removing it means giving up daily fully-automated re-auth, which is core to why the intraday auto-trade scheduler works unattended. That's a product decision, not a bug — flagging it here so it's a conscious tradeoff, not a blind spot.
- **Mitigate**: make sure `ZERODHA_TOTP_SECRET` and `ZERODHA_PASSWORD` are SSM SecureString (they are) and that the IAM role scoping is as tight as possible (`ssm:GetParameter` on `/stockbot/*` only). If you ever rotate your Zerodha password, this seed doesn't need to change, but if you ever suspect either is compromised, treat it as "attacker can log in as you" severity, not "attacker knows a password."

### 🟡 Accepted risk: raw exception text returned in API responses
Several routers return `detail=f"...: {e}"` (`routers/auth.py`, `trading_service.py` call sites) — could leak SDK/internal details to any caller holding the API key.
- **Why accepted rather than fixed now**: the only caller who will ever see these responses is you, the key-holder and sole developer/operator. Stripping error detail would make your own debugging harder for close to zero real benefit in a single-user threat model. Revisit if this ever becomes multi-user.

### 🔴 Open: no global paper-trading switch
`ACTIVE_BROKER` picks *which* broker executes live orders — there's no config flag to force simulation across the whole app. `dry_run=True` / `POST /api/trading/dry-run` is opt-in per call. The scheduler's intraday auto-entry (`scheduler_service.py:151`) always calls the real `enter_trade()`, never dry-run. Practically: a background job can place real market orders with no human in the loop, gated only by the score-based signal plus the four risk checks in `docs/TRADING_LOGIC.md` §2.
- **Recommendation if you want this**: add a `PAPER_TRADING=true/false` env var, check it once inside `trading_service.enter_trade()` right before the broker call, and route to a `broker.place_order()` stub instead of the real broker when true. This is a contained, low-risk change — happy to implement if you want it as a follow-up.

### 🟡 Accepted risk: no in-app rate limiting on the API key
Rate limiting (5/min auth, 30/min general) lives only in `nginx/conf.d/stockbot.conf`. If the API is ever reached directly — container port `8000` exposed, different reverse proxy, local dev — there's no brute-force protection at the app layer.
- **Why accepted for now**: the documented deploy path always puts nginx in front; this is a defense-in-depth gap, not an active hole, as long as port 8000 is never published to the host (`docker-compose.yml` currently uses `expose`, not `ports`, for the `api` service — correct).

### 🟡 Accepted risk: `TrustedHostMiddleware` only activates if `ALLOWED_HOSTS` is set
`main.py:71-74` — if that env var is forgotten in a prod deployment, there's no Host-header validation at the app layer (nginx's fixed `server_name` mitigates this in the documented path, but it's a silent gap if the deploy topology ever changes). Set `ALLOWED_HOSTS=yourdomain.com` in production `.env`/SSM as a matter of course — it's already supported, just make sure it's actually populated.

### 🟡 Accepted risk: `trades.json` has no integrity check
Sole source of truth for open positions/P&L, plain JSON, no signature/checksum. A corrupted or manually-edited file silently becomes "reality" on next load (`trading_service.py` broad `except Exception` on load just starts empty). Low likelihood, but worth knowing: if you ever hand-edit this file to fix a stuck position, a typo won't be caught.

### 🟡 Noted, not a vulnerability: NSE scraping impersonation
`nse_service.py` spoofs a desktop Chrome User-Agent/Referer to get past NSE India's bot detection for FII/DII data — functional necessity for an undocumented public endpoint, not a security bug in this app, but fragile and ToS-adjacent. If NSE changes their bot detection, this breaks silently; treat FII/DII data as best-effort.

### 🟡 Operational, not security: deploy user inconsistency
`deploy/stockbot.service` runs as `User=sudeep`; `.github/workflows/deploy.yml` and `deploy/setup.sh` both use `ubuntu`. Verify which user actually exists/owns `/opt/stockbot` on the real EC2 box — a mismatch here wouldn't be a vulnerability, just a "deploy silently uses the wrong permissions" bug waiting to surface.

## Checklist before merging any change to auth / secrets / order placement

- [ ] Did you add a new public (unauthenticated) path? If yes, does it verify a signature/checksum from the calling party, not just trust the body?
- [ ] Does the change touch `trading_service.enter_trade()` or the scheduler's auto-entry block? If yes, re-read `docs/TRADING_LOGIC.md` §2-3 — you're touching the one place real money moves without a human click.
- [ ] Any new secret? It goes in `backend/.env.example` as a placeholder only, real value in `.env` (gitignored) locally and pushed via `deploy/add-secrets.sh` to SSM for prod. Never a real value in a committed file — that's exactly how the API_SECRET_KEY leak happened.
- [ ] Any new broker/webhook integration? Verify it has a signature-check equivalent to what Zerodha's postback now has, before trusting its payload.
