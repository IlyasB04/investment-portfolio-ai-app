"""
Market data service layer.

Provides a unified interface for quote retrieval and instrument search.

Price resolution priority:
  1. Yahoo Finance live quote  (5 s timeout, no API key)
  2. Latest PriceSnapshot in DB (always available after first trade)
  3. Deterministic synthetic price  (always available, ticker-hash based)

The public module-level functions are thin wrappers kept for backward
compatibility.  New code should use the MarketDataService singleton.

Quote dict keys
---------------
  ticker          str
  name            str
  price           Decimal
  previous_close  Decimal | None
  change_pct      float | None
  currency        str
  exchange        str
  source          str   ("live" | "snapshot" | "synthetic")

Search result keys
------------------
  ticker   str
  name     str
  type     str
  exchange str
"""

import hashlib
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

logger = logging.getLogger(__name__)

# ── HTTP helper ────────────────────────────────────────────────────────────────

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 5


def _http_get(url: str, params: dict | None = None) -> dict | None:
    """Make a GET request and return parsed JSON, or None on any error."""
    if params:
        qs = "&".join(
            f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()
        )
        url = f"{url}?{qs}"
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as exc:
        logger.debug("HTTP fetch failed for %s: %s", url, exc)
        return None


# ── Synthetic pricing ──────────────────────────────────────────────────────────

_SYNTH_MIN = Decimal("0.85")
_SYNTH_RANGE = Decimal("0.50")      # [0.85, 1.35]
_BASE_MIN = Decimal("18.00")
_BASE_RANGE = Decimal("482.00")     # base range [$18, $500]


def _ticker_hash_ratio(ticker: str) -> Decimal:
    """Normalised [0, 1) value deterministically derived from ticker string."""
    digest = hashlib.sha256(ticker.upper().encode()).hexdigest()
    seed = int(digest[:8], 16)
    return Decimal(seed) / Decimal(0xFFFF_FFFF)


def _synthetic_price_from_cost(ticker: str, average_cost: Decimal) -> Decimal:
    """
    Deterministic price in [0.85 × avg_cost, 1.35 × avg_cost].
    Stable across requests for the same ticker.
    """
    ratio = _ticker_hash_ratio(ticker)
    multiplier = _SYNTH_MIN + ratio * _SYNTH_RANGE
    return (average_cost * multiplier).quantize(Decimal("0.0001"))


def _synthetic_price_from_ticker(ticker: str) -> Decimal:
    """
    Deterministic price in [$18, $500] derived purely from the ticker symbol.
    Used when no average_cost is available (e.g., first-ever trade on a symbol).
    """
    ratio = _ticker_hash_ratio(ticker)
    return (_BASE_MIN + ratio * _BASE_RANGE).quantize(Decimal("0.01"))


# ── Yahoo Finance provider ─────────────────────────────────────────────────────

_YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
_YAHOO_SEARCH = "https://query1.finance.yahoo.com/v1/finance/search"


def _yahoo_quote(ticker: str) -> dict | None:
    data = _http_get(
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
            "source": "live",
        }
    except (KeyError, IndexError, TypeError) as exc:
        logger.debug("Yahoo quote parse error for %s: %s", ticker, exc)
        return None


def _yahoo_search(query: str) -> list[dict]:
    data = _http_get(_YAHOO_SEARCH, {"q": query, "quotesCount": "10", "newsCount": "0"})
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


# ── Core price resolution ──────────────────────────────────────────────────────

def get_execution_price(
    ticker: str,
    average_cost: Decimal | None = None,
) -> tuple[Decimal, str]:
    """
    Return (price, source) for trade execution. NEVER raises.

    Resolution order:
      1. Yahoo Finance live quote
      2. Latest PriceSnapshot from DB
      3. Synthetic price (from average_cost if available, else from ticker hash)
    """
    ticker = ticker.upper()

    # 1. Live quote
    try:
        quote = _yahoo_quote(ticker)
        if quote and quote["price"] > 0:
            return quote["price"], "live"
    except Exception as exc:
        logger.warning("Live quote failed for %s: %s", ticker, exc)

    # 2. Latest snapshot from DB
    try:
        from .models import PriceSnapshot  # local import avoids circular deps
        snap = PriceSnapshot.objects.filter(ticker=ticker).order_by("-as_of").first()
        if snap and snap.price > 0:
            return snap.price, "snapshot"
    except Exception as exc:
        logger.warning("Snapshot lookup failed for %s: %s", ticker, exc)

    # 3. Deterministic synthetic — guaranteed to return a valid price
    if average_cost and average_cost > 0:
        price = _synthetic_price_from_cost(ticker, average_cost)
    else:
        price = _synthetic_price_from_ticker(ticker)

    logger.info("Using synthetic price for %s: %s", ticker, price)
    return price, "synthetic"


# ── Public module-level functions (backward-compatible) ────────────────────────

def get_quote(ticker: str) -> dict | None:
    """Return a live quote dict for the ticker, or None if unavailable."""
    return _yahoo_quote(ticker)


def search_instruments(query: str) -> list[dict]:
    """Return up to 10 matching EQUITY/ETF instruments for a search query."""
    return _yahoo_search(query)


# ── MarketDataService class ────────────────────────────────────────────────────

class MarketDataService:
    """
    Unified market data access.

    Usage:
        from .market_data import market_service
        quote = market_service.get_quote("AAPL")
        price, source = market_service.get_execution_price("AAPL")
    """

    def get_quote(self, ticker: str) -> dict | None:
        """
        Return a live quote dict or None if Yahoo Finance is unavailable.
        Keys: ticker, name, price (Decimal), previous_close, change_pct,
              currency, exchange, source.
        """
        return _yahoo_quote(ticker.upper())

    def get_quote_with_fallback(self, ticker: str, average_cost: Decimal | None = None) -> dict:
        """
        Always returns a quote dict — falls back to synthetic pricing.
        Adds 'source' key: "live" | "snapshot" | "synthetic".
        """
        live = self.get_quote(ticker)
        if live:
            return live

        price, source = get_execution_price(ticker, average_cost)
        return {
            "ticker": ticker.upper(),
            "name": ticker.upper(),
            "price": price,
            "previous_close": None,
            "change_pct": None,
            "currency": "USD",
            "exchange": "",
            "source": source,
        }

    def get_execution_price(
        self,
        ticker: str,
        average_cost: Decimal | None = None,
    ) -> tuple[Decimal, str]:
        """Always returns (Decimal price, source_str). Never raises."""
        return get_execution_price(ticker, average_cost)

    def search_instruments(self, query: str) -> list[dict]:
        """
        Return up to 10 matching EQUITY/ETF instruments.
        Returns empty list if Yahoo Finance is unavailable.
        """
        return _yahoo_search(query)


# Singleton for use across the app
market_service = MarketDataService()
