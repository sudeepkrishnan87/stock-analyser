# Security audit — Jarvis

Threat model: **single operator, live trading money, public GitHub repo.** The two things that matter most are (1) nobody else can ever call the API, and (2) a leaked credential can't be used to silently drain or manipulate the account. Everything else is secondary.

Audited 2026-07-16 via full reverse-engineering pass. Status legend: 🔴 open · 🟡 accepted risk (documented, not fixed) · ✅ fixed.

## Findings

### ✅ Fixed: real API_SECRET_KEY committed to git, now rotated
`backend/.env.example` contained a real `secrets.token_urlsafe(32)`-shaped key (not a `your_x_here` placeholder) since the initial commit, in a **public** repo. Anyone with repo access has always had it.
- A first pass placeholder-ed `.env.example` locally but the change was never actually committed — the real key stayed live on `main` until commit `fb060b6` (2026-07-16) fixed it for real.
- **Also done (2026-07-16)**: the live `API_SECRET_KEY` was rotated in AWS SSM (`/stockbot/API_SECRET_KEY`) and locally in `backend/.env`. Log out and back in on the frontend with the new key — the old one now 401s.
- **Still open**: the old key remains readable in git history (old commits before `fb060b6`) since it's a public repo. Rotation makes the old value harmless (it's no longer valid anywhere), but if you want the value itself gone from history, that's a separate `git filter-repo` decision — rewrites history and breaks existing clones/forks, so only do it deliberately, not as a reflex.

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

### ✅ Fixed: scheduler no longer auto-enters trades
Previously, the scheduler's intraday job (`scheduler_service.py:139-159`) called `trading_service.enter_trade()` directly on any STRONG BUY + confirmed breakout, placing a real market order with no human in the loop, gated only by the score-based signal plus the four risk checks in `docs/TRADING_LOGIC.md` §2. **Fixed (2026-07-16)**: the operator's explicit requirement is that no trade is ever placed without their approval. The job now only sends the alert (email/WhatsApp); entering the trade requires a separate, human-initiated call to the trading API. `monitor_positions()`/`exit_all_intraday()` still run unattended, since those only manage risk on positions a human already approved into.
- **Follow-up planned**: a dashboard "Pending Signals" panel with an explicit Approve/Reject action, so approval doesn't require manually re-entering trade params via the API — tracked as a separate task, not yet built.
- A global `PAPER_TRADING` switch (simulate regardless of caller) is still a separate, not-yet-implemented idea if useful later for dry-run testing independent of the approval gate.

### 🟡 Accepted risk: no in-app rate limiting on the API key
Rate limiting (5/min auth, 30/min general) lives only in `nginx/conf.d/stockbot.conf`. If the API is ever reached directly — container port `8000` exposed, different reverse proxy, local dev — there's no brute-force protection at the app layer.
- **Why accepted for now**: the documented deploy path always puts nginx in front; this is a defense-in-depth gap, not an active hole, as long as port 8000 is never published to the host (`docker-compose.yml` currently uses `expose`, not `ports`, for the `api` service — correct).

### 🟡 Accepted risk: `TrustedHostMiddleware` only activates if `ALLOWED_HOSTS` is set
`main.py:71-74` — if that env var is forgotten in a prod deployment, there's no Host-header validation at the app layer (nginx's fixed `server_name` mitigates this in the documented path, but it's a silent gap if the deploy topology ever changes). Set `ALLOWED_HOSTS=yourdomain.com` in production `.env`/SSM as a matter of course — it's already supported, just make sure it's actually populated.

### 🟡 Accepted risk: `trades.json` has no integrity check
Sole source of truth for open positions/P&L, plain JSON, no signature/checksum. A corrupted or manually-edited file silently becomes "reality" on next load (`trading_service.py` broad `except Exception` on load just starts empty). Low likelihood, but worth knowing: if you ever hand-edit this file to fix a stuck position, a typo won't be caught.
- **Partially mitigated (2026-07-17)**: `services/backup_service.py` pushes `trades.json` to a private, versioned S3 bucket (`jarvis-tradebook-backup-233903268134`, `ap-south-1`) after every save, and restores it on startup if the local file is missing (e.g. after an EC2 instance replacement — see `docs/DEPLOYMENT.md`). This protects against *loss* (instance/volume destroyed) and gives rollback-to-any-version via S3 versioning, but does **not** add a checksum/signature check on load — a corrupted file still loads as-is; you'd have to notice and manually restore an older S3 version yourself.

### 🟡 Noted, not a vulnerability: NSE scraping impersonation
`nse_service.py` spoofs a desktop Chrome User-Agent/Referer to get past NSE India's bot detection for FII/DII data — functional necessity for an undocumented public endpoint, not a security bug in this app, but fragile and ToS-adjacent. If NSE changes their bot detection, this breaks silently; treat FII/DII data as best-effort.

### 🟡 Operational, not security: deploy user inconsistency
`deploy/stockbot.service` runs as `User=sudeep`; `.github/workflows/deploy.yml` and `deploy/setup.sh` both use `ubuntu`. Verify which user actually exists/owns `/opt/stockbot` on the real EC2 box — a mismatch here wouldn't be a vulnerability, just a "deploy silently uses the wrong permissions" bug waiting to surface.

## Checklist before merging any change to auth / secrets / order placement

- [ ] Did you add a new public (unauthenticated) path? If yes, does it verify a signature/checksum from the calling party, not just trust the body?
- [ ] Does the change touch `trading_service.enter_trade()` or the scheduler's auto-entry block? If yes, re-read `docs/TRADING_LOGIC.md` §2-3 — you're touching the one place real money moves without a human click.
- [ ] Any new secret? It goes in `backend/.env.example` as a placeholder only, real value in `.env` (gitignored) locally and pushed via `deploy/add-secrets.sh` to SSM for prod. Never a real value in a committed file — that's exactly how the API_SECRET_KEY leak happened.
- [ ] Any new broker/webhook integration? Verify it has a signature-check equivalent to what Zerodha's postback now has, before trusting its payload.
