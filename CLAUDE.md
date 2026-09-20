# Jarvis — Stock Analyser & Auto-Trader

Personal, single-user algorithmic trading assistant for NSE/BSE via Zerodha Kite (primary) or Fyers (secondary). FastAPI backend + React/Vite frontend, deployed on a single EC2 box behind nginx.

This file orients Claude Code (or any engineer) fast. Deep dives live in `docs/`:

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — Mermaid diagrams of the whole system: component overview, request auth lifecycle, stock-research flow, the trading decision + human-approval loop, and the deploy pipeline. Start here if you're new to the codebase.
- **[docs/TRADING_LOGIC.md](docs/TRADING_LOGIC.md)** — how a buy/sell decision is actually made: the composite scoring engine (LONG and its bearish SHORT mirror), risk gates, position sizing, partial profit-taking, scheduler timeline, order lifecycle. Read this before touching `services/screener_service.py` or `services/trading_service.py`.
- **[docs/SECURITY.md](docs/SECURITY.md)** — threat model, current findings, what's fixed vs. accepted risk, and the checklist to run before any change that touches auth, secrets, or order placement.
- **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** — the actual, current AWS setup: EC2 access, normal vs. manual deploy, pushing secret changes to SSM, verifying a deploy, and a troubleshooting table for the failure modes already hit in practice (stopped instance, region mismatch between EC2 and SSM, stale browser key).
- **[docs/AGENTS.md](docs/AGENTS.md)** — the deterministic agent/orchestrator framework in `backend/agents/` (Phase 0 as of 2026-09-20: shadow-mode scaffolding, zero behavior change). Read this before adding a new agent or touching `agents/orchestrator.py`.
- **[docs/enrichment.md](docs/enrichment.md)** — the trading-strategy enrichment roadmap (sector concentration, daily-drawdown gate, market regime, ADX, etc.) that `backend/agents/` exists to eventually carry, one enrichment per agent.

## What this is NOT

- Not multi-user. One `X-API-Key` gates everything.
- Not backed by a database. All state is one JSON file (`backend/data/trades.json`) plus in-memory process state.
- Not paper-trading by default. `services/trading_service.enter_trade()` places **real market orders** when called (LONG or SHORT — intraday short-selling shipped 2026-08-13, always INTRADAY/MIS, see `docs/TRADING_LOGIC.md` §1a). The scheduler never calls it automatically — the 15-minute intraday job only alerts on STRONG BUY and STRONG SELL signals; entering a trade always requires an explicit, human-initiated approval (Signals tab, one-click email/WhatsApp link, or the Research tab's direct Approve action). `dry_run=True` / `POST /api/trading/dry-run` is the only simulation path, and it's opt-in per call, not a global switch.
- The Anthropic/Claude integration (`services/claude_service.py`) is narrative-only — it explains a decision already made by deterministic Python. It never decides a trade.

## Repo map

```
backend/
  main.py                  # FastAPI app, X-API-Key middleware, CORS, startup auto-login
  config.py                # Settings: env vars locally, AWS SSM Parameter Store in production
  brokers/
    base.py                # BaseBroker ABC — the contract every broker must implement
    zerodha.py              # Kite Connect v5 (default, ACTIVE_BROKER=zerodha)
    fyers.py                 # Fyers v3 (ACTIVE_BROKER=fyers, less battle-tested)
  agents/                   # Deterministic agent/orchestrator framework — see docs/AGENTS.md.
    base.py                 #   BaseAgent ABC, AgentContext, AgentResult, Verdict — every agent's contract
    tracing.py               #   run_traced() — the "logger agent," grep-friendly structured log lines
    orchestrator.py           #   Orchestrator singleton — parallel fan-out (ThreadPoolExecutor) + decision policy
    scoring_agent.py           #   ScoringAgent — wraps screener_service.scan_symbol() unchanged
  routers/                  # HTTP surface — one file per feature area (auth, stocks, scanner, trading, alerts, fii_dii)
  services/
    screener_service.py     # THE signal engine — composite LONG + SHORT scores, see docs/TRADING_LOGIC.md
    trading_service.py       # Risk gates, position sizing, order entry/exit, trailing stop
    technical_service.py     # RSI/MACD/Bollinger/SMA via `ta`
    candlestick_service.py   # Rule-based candlestick pattern detection
    elliott_wave_service.py  # Pivot detection + wave labeling + Fibonacci levels
    trendline_service.py     # Breakout/breakdown + support/resistance
    fundamental_service.py   # yfinance-based P/E, ROE, EBITDA scoring
    claude_service.py        # Anthropic narrative wrapper — descriptive, not decisioning
    auto_auth_service.py     # Scripted Zerodha web-login (TOTP) — see security doc, this is higher-risk than OAuth
    scheduler_service.py     # APScheduler cron jobs — the automation timeline
    alert_service.py         # Email (SMTP) + WhatsApp (Twilio) notifications
    nse_service.py            # FII/DII scraping + quarterly financials
  data/trades.json           # sole persisted trading state (gitignored)
frontend/
  src/App.tsx                # single-page orchestrator: LoginGate → Research / Signals / Trade Book tabs
  src/api/client.ts           # axios + X-API-Key interceptor (key stored in localStorage)
  src/components/             # SignalsPanel (approve/reject queue), TradeBook (reasoning/history),
                               # TradeSetupCard (Research tab — direct-approve any symbol, not just
                               # read-only anymore), chart/indicator/AI-narrative panels
deploy/                      # EC2 bootstrap, systemd unit, AWS SSM secret upload script
nginx/                       # reverse proxy: TLS, HSTS, rate limiting (5/min auth, 30/min api)
.github/workflows/deploy.yml # push-to-main → SSH → git pull → docker compose build/up (live, currently authoritative)
.harness/                    # Harness.io pipeline scaffold — learning/parallel track, see .harness/README.md before assuming it's wired up
docker-compose.yml           # api + frontend + nginx + certbot, single EC2 instance
.claude/skills/               # Claude Code task playbooks for this repo — see below
```

## Adding a new enrichment (new indicator/strategy)

This is the most common extension. The pattern is always the same:

1. Compute your signal in a new or existing `services/*_service.py` module — return plain dicts/floats, no side effects.
2. Add a `_your_signal_score(...)` function to `services/screener_service.py` following the existing scorers (each maxes out around 10-15 points — see `docs/TRADING_LOGIC.md` for the current weight table).
3. Wire it into the `scores = {...}` dict in `scan_symbol()` (`screener_service.py:235`) and into `result[...]` if the raw signal should also be exposed to the frontend/AI narrative.
4. If it should influence trade sizing/SL/target, extend the `if signal in ("BUY", "STRONG BUY")` block (`screener_service.py:263`) — don't touch `trading_service.py` unless you're changing risk management itself.
5. Run `python3 -m py_compile` on touched files, then hit `/api/scanner/symbol/{symbol}` locally against a real or recent-cached candle set to sanity check the new score doesn't blow up the total past 100 or break signal classification.

Use `.claude/skills/add-strategy-signal` for the guided version of this.

## Local dev

See `README.md` for full setup. Quick reference:

```bash
cd backend && uvicorn main:app --reload --port 8000
cd frontend && npm run dev
```

## Before committing anything touching secrets/auth/trading

Read `docs/SECURITY.md`'s checklist first. This app places real money orders automatically — treat changes to `trading_service.py`, `scheduler_service.py`, and anything in `brokers/` as high-blast-radius even in a "personal project."
