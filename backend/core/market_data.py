"""
Market data abstraction layer.

Primary source: Yahoo Finance public JSON endpoints (no API key required).
Fallback: deterministic synthetic pricing from views_portfolio._synthetic_price.

Swapping the provider means replacing only this file.
"""

import json
import urllib.error
import urllib.request
from decimal import Decimal

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; portfolio-app/1.0)"}
_TIMEOUT = 5

_YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
_YAHOO_SEARCH = "https://query1.finance.yahoo.com/v1/finance/search"


def _get(url: str, params: dict | None = None) -> dict | None:
    if params:
        qs = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
        url = f"{url}?{qs}"
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None


def get_quote(ticker: str) -> dict | None:
    """
    Return latest quote dict for a ticker, or None if unavailable.

    Keys: ticker, price (Decimal), previous_close (Decimal | None),
          name, currency, exchange, change_pct (float | None).
    """
    data = _get(_YAHOO_CHART.format(ticker=ticker.upper()), {"interval": "1d", "range": "1d"})
    if not data:
        return None
    try:
        result = data["chart"]["result"][0]
        meta = result["meta"]
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        if price is None:
            return None
        change_pct = ((price - prev) / prev * 100) if prev else None
        return {
            "ticker": ticker.upper(),
            "name": meta.get("longName") or meta.get("shortName") or ticker.upper(),
            "price": Decimal(str(price)),
            "previous_close": Decimal(str(prev)) if prev else None,
            "change_pct": round(change_pct, 2) if change_pct is not None else None,
            "currency": meta.get("currency", "USD"),
            "exchange": meta.get("exchangeName", ""),
        }
    except (KeyError, IndexError, TypeError):
        return None


def search_instruments(query: str) -> list[dict]:
    """
    Return up to 10 matching instruments for a search query.

    Each item: ticker, name, type, exchange.
    Filters to EQUITY and ETF types only.
    """
    data = _get(_YAHOO_SEARCH, {"q": query, "quotesCount": "10", "newsCount": "0"})
    if not data:
        return []
    results = []
    for q in data.get("quotes", []):
        q_type = q.get("quoteType", "")
        if q_type not in ("EQUITY", "ETF"):
            continue
        symbol = q.get("symbol")
        if not symbol:
            continue
        results.append({
            "ticker": symbol,
            "name": q.get("shortname") or q.get("longname") or symbol,
            "type": q_type,
            "exchange": q.get("exchange", ""),
        })
    return results
