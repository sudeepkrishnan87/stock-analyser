import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")   # development | production


def _aws_param(name: str, default: str = "") -> str:
    """
    In production, fetch secret from AWS Systems Manager Parameter Store.
    Falls back to environment variable / default in development.

    Parameters are stored as SecureString under /stockbot/<name>.
    e.g. /stockbot/KITE_API_KEY

    IAM role on EC2 must have ssm:GetParameter permission on /stockbot/* —
    no hardcoded AWS credentials needed (uses instance metadata).
    """
    env_val = os.getenv(name, "")
    if env_val:
        return env_val  # .env or environment variable takes priority

    if ENVIRONMENT != "production":
        return default

    try:
        import boto3
        ssm = boto3.client("ssm", region_name=os.getenv("AWS_REGION", "eu-north-1"))
        response = ssm.get_parameter(Name=f"/stockbot/{name}", WithDecryption=True)
        return response["Parameter"]["Value"]
    except Exception as e:
        logger.warning(f"Could not fetch /stockbot/{name} from Parameter Store: {e}")
        return default


class Settings:
    # ── Personal API key (restricts access to only you) ─────────────────────
    # Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
    API_SECRET_KEY: str = _aws_param("API_SECRET_KEY")

    # ── Zerodha Kite ─────────────────────────────────────────────────────────
    KITE_API_KEY: str = _aws_param("KITE_API_KEY")
    KITE_API_SECRET: str = _aws_param("KITE_API_SECRET")
    KITE_REDIRECT_URL: str = _aws_param("KITE_REDIRECT_URL", "http://localhost:8000/api/auth/callback")

    # ── Fyers ────────────────────────────────────────────────────────────────
    FYERS_APP_ID: str = _aws_param("FYERS_APP_ID")
    FYERS_SECRET: str = _aws_param("FYERS_SECRET")
    FYERS_REDIRECT_URL: str = _aws_param("FYERS_REDIRECT_URL", "http://localhost:8000/api/auth/fyers/callback")

    # ── AI ───────────────────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = _aws_param("ANTHROPIC_API_KEY")

    # ── Email Alerts (Gmail SMTP or any SMTP) ────────────────────────────────
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    EMAIL_SENDER: str = _aws_param("EMAIL_SENDER")
    EMAIL_PASSWORD: str = _aws_param("EMAIL_PASSWORD")
    EMAIL_RECIPIENT: str = _aws_param("EMAIL_RECIPIENT")

    # ── WhatsApp Alerts (Twilio) ─────────────────────────────────────────────
    TWILIO_ACCOUNT_SID: str = _aws_param("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN: str = _aws_param("TWILIO_AUTH_TOKEN")
    TWILIO_WHATSAPP_FROM: str = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    TWILIO_WHATSAPP_TO: str = _aws_param("TWILIO_WHATSAPP_TO")

    # ── Trading Capital & Risk Management ────────────────────────────────────
    TRADING_CAPITAL: float = float(os.getenv("TRADING_CAPITAL", "100000"))   # ₹1,00,000 default
    MAX_RISK_PER_TRADE_PCT: float = float(os.getenv("MAX_RISK_PER_TRADE_PCT", "2.0"))   # 2% per trade
    MAX_PORTFOLIO_EXPOSURE_PCT: float = float(os.getenv("MAX_PORTFOLIO_EXPOSURE_PCT", "60.0"))  # 60% deployed
    DAILY_LOSS_LIMIT_PCT: float = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "3.0"))   # Stop trading at 3% daily loss
    MAX_OPEN_POSITIONS: int = int(os.getenv("MAX_OPEN_POSITIONS", "5"))
    ACTIVE_BROKER: str = os.getenv("ACTIVE_BROKER", "zerodha")   # zerodha | fyers

    # ── Screener / Watchlist ─────────────────────────────────────────────────
    DEFAULT_WATCHLIST: list = [
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
        "HINDUNILVR", "KOTAKBANK", "SBIN", "BHARTIARTL", "ITC",
        "AXISBANK", "LT", "BAJFINANCE", "WIPRO", "SUNPHARMA",
        "TITAN", "MARUTI", "ASIANPAINT", "TECHM", "HCLTECH",
        "NTPC", "POWERGRID", "COALINDIA", "ONGC", "BPCL",
        "DIVISLAB", "CIPLA", "EICHERMOT", "NESTLEIND", "ULTRACEMCO",
    ]
    SCAN_INTERVAL_MINUTES: int = int(os.getenv("SCAN_INTERVAL_MINUTES", "15"))

    CORS_ORIGINS: list = ["http://localhost:5173", "http://localhost:3000"]

    # ── In-memory session tokens ─────────────────────────────────────────────
    _kite_access_token: str = ""
    _fyers_access_token: str = ""

    @classmethod
    def set_access_token(cls, token: str):
        cls._kite_access_token = token

    @classmethod
    def get_access_token(cls) -> str:
        return cls._kite_access_token

    @classmethod
    def is_authenticated(cls) -> bool:
        return bool(cls._kite_access_token)

    @classmethod
    def clear_token(cls):
        cls._kite_access_token = ""

    @classmethod
    def set_fyers_token(cls, token: str):
        cls._fyers_access_token = token

    @classmethod
    def get_fyers_token(cls) -> str:
        return cls._fyers_access_token

    @classmethod
    def is_fyers_authenticated(cls) -> bool:
        return bool(cls._fyers_access_token)


settings = Settings()
