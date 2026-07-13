from fastapi import APIRouter, Query
from typing import List
from services.nse_service import fetch_fii_dii_data

router = APIRouter()


@router.get("/")
def get_fii_dii(days: int = Query(default=30, ge=5, le=90)):
    """Fetch FII/DII net activity for the last N trading days from NSE India."""
    data = fetch_fii_dii_data(days=days)
    return {"data": data, "count": len(data)}
