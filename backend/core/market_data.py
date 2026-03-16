"""
Market data service layer.

Provides a single interface for quote retrieval and instrument search.
Active provider: Yahoo Finance (public JSON endpoints, no API key required).

To swap providers, replace _yahoo_quote / _yahoo_search with your own
implementation while keeping the public interface (get_quote / search_instruments)
unchanged.

Quote dict keys:
    ticker (str), name (str), price (Decimal),
    previous_close (Decimal | None), change_pct (float | None),
    currency (str), exchange (str)

Search result keys:
    ticker (str), name (str), type (str), exchange (str)
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

# ── HTTP helper ────────────────────────────────────────────────────────────────

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; portfolio-app/1.0)"}
_TIMEOUT = 5


def _get(url: str, params: dict | None = None) -> dict | None:
    if params:
        qs = "&".join(
            f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()
        )
        url = f"{url}?{qs}"
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError):
        return None


# ── Yahoo Finance provider ─────────────────────────────────────────────────────

_YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
_YAHOO_SEARCH = "https://query1.finance.yahoo.com/v1/finance/search"


def _yahoo_quote(ticker: str) -> dict | None:
    data = _get(
        _YAHOO_CHART.format(ticker=ticker.upper()),
        {"interval": "1d", "range": "1d"},
    )
    if not data:
        return None
    try:
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        if price is None:
            return None
        change_pct = round((price - prev) / prev * 100, 2) if prev else None
        return {
            "ticker": ticker.upper(),
            "name": meta.get("longName") or meta.get("shortName") or ticker.upper(),
            "price": Decimal(str(price)),
            "previous_close": Decimal(str(prev)) if prev else None,
            "change_pct": change_pct,
            "currency": meta.get("currency", "USD"),
            "exchange": meta.get("exchangeName", ""),
        }
    except (KeyError, IndexError, TypeError):
        return None


def _yahoo_search(query: str) -> list[dict]:
    data = _get(_YAHOO_SEARCH, {"q": query, "quotesCount": "10", "newsCount": "0"})
    if not data:
        return []
    results = []
    for item in data.get("quotes", []):
        q_type = item.get("quoteType", "")
        if q_type not in ("EQUITY", "ETF"):
            continue
        symbol = item.get("symbol")
        if not symbol:
            continue
        results.append({
            "ticker": symbol,
            "name": item.get("shortname") or item.get("longname") or symbol,
            "type": q_type,
            "exchange": item.get("exchange", ""),
        })
    return results


# ── Public interface ───────────────────────────────────────────────────────────

def get_quote(ticker: str) -> dict | None:
    """Return a live quote dict for the ticker, or None if unavailable."""
    return _yahoo_quote(ticker)


def search_instruments(query: str) -> list[dict]:
    """Return up to 10 matching EQUITY/ETF instruments for a search query."""
    return _yahoo_search(query)
