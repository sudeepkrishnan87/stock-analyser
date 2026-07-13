import httpx
import yfinance as yf
from datetime import datetime
from typing import List, Dict, Optional

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "DNT": "1",
}


def fetch_fii_dii_data(days: int = 30) -> List[Dict]:
    """
    Fetch FII/DII daily net activity from NSE India.
    Returns list of {date, fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net}.
    """
    try:
        with httpx.Client(headers=NSE_HEADERS, follow_redirects=True, timeout=20) as client:
            # Get cookies from NSE homepage first
            client.get("https://www.nseindia.com/")

            response = client.get("https://www.nseindia.com/api/fiidiiTradeReact")
            response.raise_for_status()
            raw = response.json()

        # Group by date: each date has FII and DII entries
        grouped: Dict[str, Dict] = {}
        for entry in raw:
            date_str = entry.get("date", "")
            if not date_str:
                continue

            category = entry.get("category", entry.get("clientType", "")).upper()
            buy_val = float(entry.get("buyValue", 0) or 0)
            sell_val = float(entry.get("sellValue", 0) or 0)
            net_val = float(entry.get("netValue", 0) or 0)

            if date_str not in grouped:
                grouped[date_str] = {
                    "date": date_str,
                    "fii_buy": 0, "fii_sell": 0, "fii_net": 0,
                    "dii_buy": 0, "dii_sell": 0, "dii_net": 0,
                }

            if "FII" in category or "FPI" in category:
                grouped[date_str]["fii_buy"] = round(buy_val, 2)
                grouped[date_str]["fii_sell"] = round(sell_val, 2)
                grouped[date_str]["fii_net"] = round(net_val, 2)
            elif "DII" in category:
                grouped[date_str]["dii_buy"] = round(buy_val, 2)
                grouped[date_str]["dii_sell"] = round(sell_val, 2)
                grouped[date_str]["dii_net"] = round(net_val, 2)

        result = sorted(grouped.values(), key=lambda x: x["date"])
        return result[-days:] if len(result) > days else result

    except Exception:
        return []


def fetch_quarterly_results(symbol: str) -> List[Dict]:
    """
    Fetch quarterly financial results using yfinance.
    Returns last 4 quarters of revenue, net profit, EPS.
    """
    try:
        ticker_symbol = f"{symbol.upper()}.NS"
        ticker = yf.Ticker(ticker_symbol)

        # Get quarterly income statement
        q_income = ticker.quarterly_income_stmt
        if q_income is None or q_income.empty:
            return []

        results = []
        columns = list(q_income.columns)[:4]  # Last 4 quarters

        for col in columns:
            quarter_label = col.strftime("Q%m %Y") if hasattr(col, "strftime") else str(col)[:10]

            revenue = None
            net_profit = None
            eps = None

            # Revenue row
            for rev_key in ["Total Revenue", "Revenue", "Net Sales"]:
                if rev_key in q_income.index:
                    val = q_income.loc[rev_key, col]
                    if val and not (hasattr(val, '__float__') and float(val) != float(val)):
                        revenue = round(float(val) / 1e7, 2)  # Convert to crores
                    break

            # Net income row
            for ni_key in ["Net Income", "Net Income Common Stockholders"]:
                if ni_key in q_income.index:
                    val = q_income.loc[ni_key, col]
                    if val and not (hasattr(val, '__float__') and float(val) != float(val)):
                        net_profit = round(float(val) / 1e7, 2)
                    break

            results.append({
                "quarter": quarter_label,
                "revenue": revenue,
                "net_profit": net_profit,
                "eps": eps,
            })

        return results

    except Exception:
        return []
