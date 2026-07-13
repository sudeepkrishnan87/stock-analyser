"""
Fundamental screening: P/E, P/B, EBITDA margin, Revenue growth,
Net profit margin, Debt/Equity, Promoter holding.

Data source: yfinance (free, no API key needed).
NSE symbols need ".NS" suffix for yfinance.
"""

import yfinance as yf
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


def _yf_ticker(symbol: str) -> yf.Ticker:
    sym = symbol.upper().strip()
    if not sym.endswith(".NS") and not sym.endswith(".BO"):
        sym = sym + ".NS"
    return yf.Ticker(sym)


def fetch_fundamentals(symbol: str) -> Dict:
    """
    Fetch key fundamental data for a stock.

    Returns a dict with all available fundamental metrics and a
    composite FUNDAMENTAL_SCORE (0-100) based on value + quality criteria.
    """
    try:
        ticker = _yf_ticker(symbol)
        info = ticker.info or {}
    except Exception as e:
        logger.warning(f"yfinance info fetch failed for {symbol}: {e}")
        return {"symbol": symbol, "error": str(e), "fundamental_score": 0}

    # ── Raw metrics ───────────────────────────────────────────────────────
    pe = info.get("trailingPE") or info.get("forwardPE")
    pb = info.get("priceToBook")
    eps = info.get("trailingEps")
    revenue = info.get("totalRevenue")
    net_income = info.get("netIncomeToCommon")
    ebitda = info.get("ebitda")
    total_debt = info.get("totalDebt", 0) or 0
    equity = info.get("totalStockholderEquity") or info.get("bookValue", 1)
    market_cap = info.get("marketCap")
    dividend_yield = info.get("dividendYield")
    roe = info.get("returnOnEquity")
    revenue_growth = info.get("revenueGrowth")       # YoY quarterly
    earnings_growth = info.get("earningsGrowth")     # YoY quarterly
    gross_margin = info.get("grossMargins")
    operating_margin = info.get("operatingMargins")
    profit_margin = info.get("profitMargins")
    current_ratio = info.get("currentRatio")
    quick_ratio = info.get("quickRatio")
    debt_to_equity = info.get("debtToEquity")        # already as ratio
    beta = info.get("beta")
    sector = info.get("sector", "")
    industry = info.get("industry", "")
    company_name = info.get("longName", symbol)

    # ── EBITDA margin ─────────────────────────────────────────────────────
    ebitda_margin = None
    if ebitda and revenue and revenue > 0:
        ebitda_margin = round(ebitda / revenue * 100, 2)

    # ── Net profit margin ─────────────────────────────────────────────────
    net_margin = None
    if profit_margin is not None:
        net_margin = round(float(profit_margin) * 100, 2)

    # ── D/E ratio ─────────────────────────────────────────────────────────
    de_ratio = None
    if debt_to_equity is not None:
        de_ratio = round(float(debt_to_equity) / 100, 2)  # yfinance gives it as pct
    elif equity and equity > 0 and total_debt is not None:
        de_ratio = round(total_debt / equity, 2)

    # ── Revenue growth % ─────────────────────────────────────────────────
    rev_growth_pct = round(float(revenue_growth) * 100, 2) if revenue_growth is not None else None
    earn_growth_pct = round(float(earnings_growth) * 100, 2) if earnings_growth is not None else None
    roe_pct = round(float(roe) * 100, 2) if roe is not None else None

    # ── Composite Fundamental Score (0-100) ──────────────────────────────
    score = _compute_fundamental_score(
        pe=pe, pb=pb, roe_pct=roe_pct, ebitda_margin=ebitda_margin,
        net_margin=net_margin, de_ratio=de_ratio,
        rev_growth_pct=rev_growth_pct, earn_growth_pct=earn_growth_pct,
        current_ratio=current_ratio,
    )

    return {
        "symbol": symbol,
        "company_name": company_name,
        "sector": sector,
        "industry": industry,
        "market_cap": market_cap,
        "pe_ratio": round(float(pe), 2) if pe else None,
        "pb_ratio": round(float(pb), 2) if pb else None,
        "eps": round(float(eps), 2) if eps else None,
        "ebitda": ebitda,
        "ebitda_margin_pct": ebitda_margin,
        "revenue": revenue,
        "net_income": net_income,
        "net_margin_pct": net_margin,
        "gross_margin_pct": round(float(gross_margin) * 100, 2) if gross_margin else None,
        "operating_margin_pct": round(float(operating_margin) * 100, 2) if operating_margin else None,
        "roe_pct": roe_pct,
        "de_ratio": de_ratio,
        "current_ratio": round(float(current_ratio), 2) if current_ratio else None,
        "quick_ratio": round(float(quick_ratio), 2) if quick_ratio else None,
        "revenue_growth_pct": rev_growth_pct,
        "earnings_growth_pct": earn_growth_pct,
        "dividend_yield_pct": round(float(dividend_yield) * 100, 2) if dividend_yield else None,
        "beta": round(float(beta), 2) if beta else None,
        "fundamental_score": score,
        "fundamental_grade": _grade(score),
    }


def _compute_fundamental_score(
    pe: Optional[float],
    pb: Optional[float],
    roe_pct: Optional[float],
    ebitda_margin: Optional[float],
    net_margin: Optional[float],
    de_ratio: Optional[float],
    rev_growth_pct: Optional[float],
    earn_growth_pct: Optional[float],
    current_ratio: Optional[float],
) -> int:
    """
    Score = sum of sub-scores across 8 dimensions, max 100.

    Weights reflect importance for swing-trade selection:
    - Valuation  (PE, PB):           25 pts
    - Profitability (ROE, margins):  25 pts
    - Growth (revenue, earnings):    20 pts
    - Balance sheet (DE, CR):        15 pts
    - EBITDA quality:                15 pts
    """
    score = 0

    # ── Valuation (25 pts) ────────────────────────────────────────────────
    if pe is not None:
        if pe <= 10:   score += 15
        elif pe <= 20: score += 12
        elif pe <= 30: score += 8
        elif pe <= 40: score += 4
        # PE > 40: 0
    if pb is not None:
        if pb <= 1:    score += 10
        elif pb <= 3:  score += 7
        elif pb <= 5:  score += 4
        elif pb <= 8:  score += 2

    # ── Profitability (25 pts) ────────────────────────────────────────────
    if roe_pct is not None:
        if roe_pct >= 25:   score += 10
        elif roe_pct >= 15: score += 7
        elif roe_pct >= 10: score += 4
        elif roe_pct >= 5:  score += 2
    if net_margin is not None:
        if net_margin >= 20:   score += 8
        elif net_margin >= 12: score += 6
        elif net_margin >= 6:  score += 3
        elif net_margin >= 2:  score += 1
    if ebitda_margin is not None:
        if ebitda_margin >= 30: score += 7
        elif ebitda_margin >= 20: score += 5
        elif ebitda_margin >= 10: score += 2

    # ── Growth (20 pts) ───────────────────────────────────────────────────
    if rev_growth_pct is not None:
        if rev_growth_pct >= 25:  score += 10
        elif rev_growth_pct >= 15: score += 7
        elif rev_growth_pct >= 8:  score += 4
        elif rev_growth_pct >= 0:  score += 2
    if earn_growth_pct is not None:
        if earn_growth_pct >= 25:  score += 10
        elif earn_growth_pct >= 15: score += 7
        elif earn_growth_pct >= 8:  score += 4
        elif earn_growth_pct >= 0:  score += 2

    # ── Balance Sheet (15 pts) ────────────────────────────────────────────
    if de_ratio is not None:
        if de_ratio <= 0.3:   score += 8
        elif de_ratio <= 0.7: score += 6
        elif de_ratio <= 1.2: score += 3
        elif de_ratio <= 2.0: score += 1
    if current_ratio is not None:
        if current_ratio >= 2.0:  score += 7
        elif current_ratio >= 1.5: score += 5
        elif current_ratio >= 1.0: score += 2

    return min(score, 100)


def _grade(score: int) -> str:
    if score >= 80: return "A+"
    if score >= 65: return "A"
    if score >= 50: return "B"
    if score >= 35: return "C"
    return "D"


def is_fundamentally_strong(fundamentals: Dict, min_score: int = 50) -> bool:
    """Quick gate: True if stock passes minimum fundamental quality bar."""
    score = fundamentals.get("fundamental_score", 0)
    pe = fundamentals.get("pe_ratio")
    # Reject PE > 60 (extremely expensive unless hypergrowth)
    if pe and pe > 60:
        return False
    return score >= min_score


def screen_by_fundamentals(symbols: list, min_score: int = 50) -> list:
    """
    Fetch fundamentals for all symbols and return those passing the quality bar.
    Returns sorted list of (symbol, fundamentals_dict) by score descending.
    """
    results = []
    for sym in symbols:
        try:
            fd = fetch_fundamentals(sym)
            if is_fundamentally_strong(fd, min_score):
                results.append(fd)
        except Exception as e:
            logger.warning(f"Fundamental screen failed for {sym}: {e}")
    return sorted(results, key=lambda x: -x.get("fundamental_score", 0))
