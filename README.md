# Jarvis — AI Stock Trading Bot

Personal algorithmic trading assistant for Indian markets (NSE/BSE) using Zerodha Kite and Fyers APIs.

## What it does

- **9-strategy composite scoring** — Volume spike, RSI, Bollinger Bands, MACD, SMA trend, Elliott Wave, trendline breakout, candlestick patterns, fundamentals (P/E, EBITDA, ROE)
- **Automated scanning** — Pre-market picks at 9 AM, intraday every 15 min, EOD swing picks at 3:45 PM
- **Auto trading** — Enters STRONG BUY signals automatically during market hours
- **Risk management** — 2% risk per trade, 3% daily loss limit, 60% max exposure, trailing stop-loss
- **Alerts** — Email + WhatsApp notifications for breakouts, trades, and daily P&L report
- **Single-user secured** — All requests require `X-API-Key` header

---

## Architecture

```
Browser (React + TailwindCSS)
    ↓  HTTPS
Nginx (SSL termination + rate limiting)
    ↓
FastAPI backend (Python 3.12)
    ├── Zerodha Kite v5
    ├── Fyers API v3
    ├── APScheduler (5 market-hours jobs)
    ├── AWS SSM Parameter Store (secrets)
    └── yfinance (fundamentals)
```

---

## Local Development

### Prerequisites

- Python 3.12+ with conda or venv
- Node.js 20+
- Zerodha Kite developer account with API key

### 1. Clone and set up backend

```bash
git clone https://github.com/sudeepkrishnan87/stock-analyser.git
cd stock-analyser

# Create and activate environment
conda create -n stockbot python=3.12
conda activate stockbot

# Install dependencies
pip install -r backend/requirements.txt
```

### 2. Configure environment

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` and fill in:

```env
API_SECRET_KEY=your_random_key        # generate: python -c "import secrets; print(secrets.token_urlsafe(32))"
KITE_API_KEY=your_kite_api_key
KITE_API_SECRET=your_kite_api_secret
KITE_REDIRECT_URL=http://localhost:8000/api/auth/callback
ANTHROPIC_API_KEY=your_anthropic_key
EMAIL_RECIPIENT=your@email.com
TRADING_CAPITAL=100000
ENVIRONMENT=development
```

### 3. Start backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Verify: http://localhost:8000/api/health

### 4. Start frontend

```bash
cd frontend
npm install
npm run dev
```

Open: http://localhost:5173

### 5. Set API key in browser

When the UI loads, enter your `API_SECRET_KEY` from `.env`. It's saved in localStorage — you only do this once.

### 6. Authenticate Zerodha daily

Zerodha tokens expire every midnight. Each trading day:

1. In Zerodha developer console → set Redirect URL to `http://localhost:8000/api/auth/callback`
2. Call `GET /api/auth/login-url` (or click Login in the UI)
3. Log in via browser → token auto-set on redirect

---

## Project Structure

```
stock-analyser/
├── backend/
│   ├── main.py                  # FastAPI app, auth middleware, scheduler startup
│   ├── config.py                # Settings, AWS Parameter Store integration
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── brokers/
│   │   ├── base.py              # Abstract broker interface
│   │   ├── zerodha.py           # Kite v5 implementation
│   │   └── fyers.py             # Fyers v3 implementation
│   ├── routers/
│   │   ├── auth.py              # Zerodha + Fyers OAuth flows
│   │   ├── stocks.py            # Stock analysis endpoint
│   │   ├── scanner.py           # Watchlist + intraday scanner
│   │   ├── trading.py           # Portfolio, positions, trade entry/exit
│   │   ├── alerts.py            # Alert history, test endpoints
│   │   └── fii_dii.py           # FII/DII flow data
│   └── services/
│       ├── screener_service.py  # 9-strategy composite scorer
│       ├── trading_service.py   # Position sizing, risk management
│       ├── trendline_service.py # Breakout/breakdown detection
│       ├── fundamental_service.py # P/E, EBITDA, ROE via yfinance
│       ├── alert_service.py     # Email + WhatsApp alerts
│       └── scheduler_service.py # APScheduler market-hours jobs
└── frontend/
    ├── src/
    │   ├── App.tsx
    │   ├── api/client.ts        # Axios with X-API-Key interceptor
    │   ├── components/
    │   │   ├── MultiTimeframeChart.tsx   # Daily/Weekly/Monthly candlestick
    │   │   ├── TechnicalIndicatorsPanel.tsx
    │   │   ├── AIAnalysisPanel.tsx
    │   │   ├── FiiDiiChart.tsx
    │   │   └── TokenSetup.tsx   # API key + Zerodha auth UI
    │   └── types/index.ts
    └── Dockerfile               # Multi-stage: node build → nginx serve
```

---

## API Endpoints

All endpoints require `X-API-Key: <your_key>` header except health and broker callbacks.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check (public) |
| GET | `/api/auth/login-url` | Get Zerodha login URL |
| GET | `/api/auth/callback` | Zerodha OAuth callback (public) |
| GET | `/api/auth/status` | Zerodha auth status |
| GET | `/api/auth/exchange?request_token=X` | Manual token exchange fallback |
| GET | `/api/scanner/watchlist` | Scan NIFTY 30 stocks |
| GET | `/api/scanner/symbol/{symbol}` | Scan single stock |
| GET | `/api/scanner/intraday` | 15-min intraday scan |
| GET | `/api/trading/portfolio` | Portfolio summary |
| GET | `/api/trading/positions` | Open positions |
| POST | `/api/trading/enter` | Enter a trade |
| POST | `/api/trading/exit/{symbol}` | Exit a trade |
| GET | `/api/alerts/history` | Last 200 alerts |
| POST | `/api/alerts/test/email` | Send test email |

---

## Automated Schedule (IST, Mon–Fri)

| Time | Job |
|------|-----|
| 9:00 AM | Pre-market scan → email top 5 picks |
| 9:15 AM – 3:15 PM | Intraday scan every 15 min, auto-enter STRONG BUY |
| 3:15 PM | Square off all MIS (intraday) positions |
| 3:35 PM | Daily P&L report via email/WhatsApp |
| 3:45 PM | EOD swing scan → email next-day picks |

---

## AWS Production Deployment

### Infrastructure

- EC2 t3.micro (eu-north-1 Stockholm) — ~$10.45/month
- Nginx + Let's Encrypt SSL
- AWS SSM Parameter Store (encrypted secrets, no `.env` on server)
- GitHub Actions CI/CD (auto-deploy on push to `main`)

### One-time EC2 bootstrap

```bash
# From your Mac — copy and run setup script
scp -i ~/Downloads/stockbot-key.pem deploy/setup.sh ubuntu@YOUR_EC2_IP:~/
ssh -i ~/Downloads/stockbot-key.pem ubuntu@YOUR_EC2_IP
bash ~/setup.sh https://github.com/sudeepkrishnan87/stock-analyser.git jarvis.mytechexp.com
```

### Upload secrets

```bash
# Fills in .env first, then:
./deploy/add-secrets.sh
# Uploads all secrets to AWS Parameter Store (eu-north-1)
# EC2 reads them via IAM role — no .env file on server
```

### GitHub Actions CI/CD

Add these secrets in GitHub → Settings → Secrets → Actions:

| Secret | Value |
|--------|-------|
| `EC2_HOST` | Your EC2 Elastic IP |
| `EC2_SSH_KEY` | Contents of your `.pem` file |

Every push to `main` → auto SSH → `git pull` → `docker compose build` → rolling restart.

### Daily Zerodha re-auth (production)

```
https://jarvis.mytechexp.com/api/auth/login-url  (with X-API-Key header)
→ opens Kite login
→ auto-redirects to https://jarvis.mytechexp.com/api/auth/callback
→ token set, Jarvis operational
```

---

## Security

- Single-user API key enforced at middleware level on every request
- Broker OAuth callbacks whitelisted (brokers can't add custom headers)
- All secrets encrypted in AWS SSM Parameter Store (AES-256)
- Nginx: TLS 1.2/1.3 only, HSTS, rate limiting (5 req/min auth, 30 req/min API)
- EC2: SSH key-only, root login disabled, UFW firewall (22/80/443 only)
- No credentials in Git — `.env` is gitignored, secrets live in Parameter Store

---

## Adding Email & WhatsApp Alerts

**Email (Gmail):**
1. Enable 2FA on Gmail
2. Generate App Password: myaccount.google.com/apppasswords
3. Add to `.env`: `EMAIL_SENDER=yourbot@gmail.com`, `EMAIL_PASSWORD=xxxx xxxx xxxx xxxx`
4. Run `./deploy/add-secrets.sh` to sync to AWS

**WhatsApp (Twilio):**
1. Sign up at twilio.com → Messaging → WhatsApp sandbox
2. Text the join code to +1 (415) 523-8886 from your WhatsApp
3. Add to `.env`: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_TO=whatsapp:+91XXXXXXXXXX`
4. Run `./deploy/add-secrets.sh`
