"""
Off-instance backup for the trade book (backend/data/trades.json).

The file already survives container rebuilds via the `trade-data` Docker
volume (EBS-backed) — this module protects against the case that doesn't:
the EC2 instance itself being replaced/terminated, or the volume being lost.

Production only (ENVIRONMENT=production) — local dev never touches the
real S3 bucket, same guard pattern as config.py's _aws_param(). Any S3
failure is logged and swallowed; a backup problem must never block a
trade from being recorded locally.
"""

import logging
import os

from config import settings, ENVIRONMENT

logger = logging.getLogger(__name__)

_S3_KEY = "trades.json"


def _enabled() -> bool:
    return ENVIRONMENT == "production" and bool(settings.TRADE_BACKUP_BUCKET)


def backup_trades_file(local_path: str) -> None:
    """Push the current trades.json to S3. Call after every local save()."""
    if not _enabled():
        return
    try:
        import boto3
        s3 = boto3.client("s3", region_name=settings.TRADE_BACKUP_REGION)
        s3.upload_file(local_path, settings.TRADE_BACKUP_BUCKET, _S3_KEY)
    except Exception as e:
        logger.error(f"[BACKUP] Could not push trade book to S3: {e}")


def restore_trades_file_if_missing(local_path: str) -> None:
    """
    On startup, if the local file doesn't exist (fresh volume / replaced
    instance), pull the last known-good copy from S3 so trade history isn't
    silently lost. No-op if a local file already exists — S3 never overwrites
    a live local copy.
    """
    if os.path.exists(local_path) or not _enabled():
        return
    try:
        import boto3
        s3 = boto3.client("s3", region_name=settings.TRADE_BACKUP_REGION)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        s3.download_file(settings.TRADE_BACKUP_BUCKET, _S3_KEY, local_path)
        logger.info("[BACKUP] Restored trade book from S3 (local file was missing).")
    except Exception as e:
        logger.warning(f"[BACKUP] No trade book restored from S3 (may not exist yet): {e}")
