---
name: deploy-check
description: This skill should be used when the user asks to "deploy", "check if this is safe to deploy", "push to main", "ship this change", or before merging any change that touches backend/routers, backend/services, backend/brokers, or docker-compose.yml / nginx config — since a push to main auto-deploys to the live trading system with no test gate.
version: 0.1.0
---

# Pre-deploy check for Jarvis

`.github/workflows/deploy.yml` triggers on every push to `main`: SSH into the EC2 box → `git pull` → `docker compose build api frontend` → `docker compose up -d` → wait 15s → curl `/api/health`. **There is no lint, type-check, or test step in CI today**, and no automatic rollback if the new container starts but is broken in a way `/api/health` doesn't catch (health only checks the scheduler/broker-auth-flag shape, not that trading logic actually works). Treat every push to `main` as an immediate production deploy of a system that places real money orders.

## Before pushing to main

1. **Compile-check everything touched:**
   ```bash
   cd backend && python3 -m py_compile $(git diff --name-only main -- '*.py')
   ```

2. **If the diff touches `services/trading_service.py`, `services/scheduler_service.py`, or anything in `brokers/`** — the highest-blast-radius files in the repo (see `CLAUDE.md`'s "What this is NOT" section) — manually exercise the change locally first:
   ```bash
   cd backend && uvicorn main:app --reload --port 8000
   ```
   Then hit `POST /api/trading/dry-run` (never a live order) with realistic entry/stop_loss/target values and confirm the response shape and sizing math match expectations. If the change affects `screener_service.py`'s scoring, hit `GET /api/scanner/symbol/{symbol}` for 2-3 real symbols and sanity-check `signal_score`/`score_breakdown`/`signal` didn't move in a way you can't explain (see `docs/TRADING_LOGIC.md` §1 for the known 130-point-ceiling quirk to keep in mind here).

3. **If the diff touches auth, secrets, or adds a new public/unauthenticated route** — walk `docs/SECURITY.md`'s checklist at the bottom of that file before pushing. A new public webhook without signature verification is exactly the class of bug that was just fixed for the Zerodha postback.

4. **If the diff touches `docker-compose.yml`, `nginx/`, or `deploy/`** — these aren't exercised by the app's own health check at all; the safest verification is running `docker compose config` locally to catch YAML/interpolation errors before they surface only after a live `git pull` on the EC2 box:
   ```bash
   docker compose config > /dev/null && echo "compose file valid"
   ```

5. **Confirm no secret is in the diff** — this is the single most consequential mistake possible in this repo (see `docs/SECURITY.md`'s leaked-key finding):
   ```bash
   git diff main -- backend/.env.example   # should never show a real-looking value, only your_x_here placeholders
   git status                              # backend/.env itself must never appear here — check .gitignore is doing its job
   ```

6. **After confirming the above, if the user wants to actually push**: this is a "push to shared/production" action — confirm with the user before running `git push`, per this repo's live-trading blast radius, even if they've asked you to make the code change itself autonomously.

## After deploy

Watch the GitHub Actions run (`gh run watch` if `gh` is available, otherwise the Actions tab) — it fails loudly on a bad build or a failing `/api/health` curl, but it will **not** catch a container that builds fine, passes health, and then places a bad trade at the next scheduler tick. For any change to the auto-trade path specifically, check back after the next `job_intraday_scan` run (every 15 min, 09:15–15:15 IST, Mon-Fri) rather than assuming a green CI run means the trading logic is correct.
