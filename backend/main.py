import hmac
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from config import settings, ENVIRONMENT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

from routers import auth, stocks, fii_dii
from routers import scanner, trading, alerts as alerts_router

# ── Paths that skip API-key check ─────────────────────────────────────────────
# Broker callbacks come from Zerodha/Fyers servers — they can't send our key.
# Health is needed by Docker and AWS ALB health checks.
_PUBLIC_PATHS = {
    "/api/health",
    "/api/auth/callback",           # Zerodha login redirect
    "/api/auth/postback",           # Zerodha order webhook
    "/api/auth/fyers/callback",     # Fyers login redirect
    "/api/auth/fyers/postback",     # Fyers order webhook
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting StockBot API — environment={ENVIRONMENT}")
    from services.scheduler_service import start_scheduler, stop_scheduler
    start_scheduler()

    # Auto-login on startup so a backend restart doesn't leave us unauthenticated
    # until the next 8:30 AM scheduler run.
    import asyncio
    from services.auto_auth_service import auto_login_zerodha
    async def _startup_login():
        await asyncio.sleep(2)  # give the server a moment to finish binding
        if settings.ZERODHA_USER_ID and settings.ZERODHA_PASSWORD and settings.ZERODHA_TOTP_SECRET:
            logger.info("Startup auto-login: attempting Zerodha authentication...")
            ok, msg = await auto_login_zerodha()
            logger.info(f"Startup auto-login: {msg}")
        else:
            logger.info("Startup auto-login skipped — ZERODHA_USER_ID/PASSWORD/TOTP_SECRET not configured.")
    asyncio.create_task(_startup_login())

    yield
    stop_scheduler()
    logger.info("StockBot API shut down.")


# Hide docs in production (no one should browse your trading API)
app = FastAPI(
    title="Stock Analyser & Auto-Trader API",
    version="2.0.0",
    lifespan=lifespan,
    docs_url=None if ENVIRONMENT == "production" else "/docs",
    redoc_url=None if ENVIRONMENT == "production" else "/redoc",
    openapi_url=None if ENVIRONMENT == "production" else "/openapi.json",
)

# ── Trusted hosts (production: only your domain) ───────────────────────────
if ENVIRONMENT == "production":
    allowed_hosts = [h for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h]
    if allowed_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

# ── CORS ───────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)

# ── API key auth middleware ────────────────────────────────────────────────
@app.middleware("http")
async def require_api_key(request: Request, call_next):
    path = request.url.path

    # Allow public paths without a key
    if path in _PUBLIC_PATHS:
        return await call_next(request)

    # Check X-API-Key header
    api_key = request.headers.get("X-API-Key", "")
    expected = settings.API_SECRET_KEY

    if not expected:
        # Key not configured — block everything to prevent open access
        logger.critical("API_SECRET_KEY is not set! Blocking all requests.")
        return JSONResponse(status_code=503, content={"detail": "Server not configured."})

    if not hmac.compare_digest(api_key, expected):
        ip = request.client.host if request.client else "unknown"
        logger.warning(f"Unauthorized request to {path} from {ip}")
        return JSONResponse(status_code=401, content={"detail": "Unauthorized."})

    return await call_next(request)


# ── Request logging + latency middleware ───────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response: Response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    logger.info(
        f"{request.method} {request.url.path} → {response.status_code} ({ms:.0f}ms) "
        f"[{request.client.host if request.client else 'unknown'}]"
    )
    return response

# ── Existing routes ───────────────────────────────────────────────────────────
app.include_router(auth.router,    prefix="/api/auth",    tags=["Authentication"])
app.include_router(stocks.router,  prefix="/api/stock",   tags=["Stock Analysis"])
app.include_router(fii_dii.router, prefix="/api/fii-dii", tags=["FII/DII"])

# ── New routes ────────────────────────────────────────────────────────────────
app.include_router(scanner.router,       prefix="/api/scanner",  tags=["Scanner"])
app.include_router(trading.router,       prefix="/api/trading",  tags=["Trading"])
app.include_router(alerts_router.router, prefix="/api/alerts",   tags=["Alerts"])


@app.get("/api/health")
def health():
    from services.scheduler_service import get_scheduler_status
    return {
        "status": "ok",
        "version": "2.0.0",
        "scheduler": get_scheduler_status(),
        "active_broker": settings.ACTIVE_BROKER,
        "zerodha_authenticated": settings.is_authenticated(),
        "fyers_authenticated": settings.is_fyers_authenticated(),
    }


if __name__ == "__main__":
    import uvicorn
    import os
    reload = ENVIRONMENT != "production"
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=reload)
