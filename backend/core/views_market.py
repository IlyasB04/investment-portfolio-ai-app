from django.http import JsonResponse
from rest_framework.decorators import api_view

from .market_data import get_execution_price, get_quote, search_instruments
from .models import PriceSnapshot
from .simulator import ensure_tracked, get_all_prices


@api_view(["GET"])
def quote(request, ticker: str):
    """
    GET /api/market/quote/<ticker>/

    Returns live quote from Yahoo Finance.
    Falls back to latest PriceSnapshot, then deterministic synthetic price.
    Always returns a valid numeric price — never returns price: null.
    """
    ticker = ticker.strip().upper()
    live = get_quote(ticker)

    if live:
        return JsonResponse({
            **live,
            "price": str(live["price"]),
            "previous_close": str(live["previous_close"]) if live["previous_close"] else None,
            "source": "live",
        })

    # Fallback 1: stored snapshot
    snapshot = PriceSnapshot.objects.filter(ticker=ticker).order_by("-as_of").first()
    if snapshot:
        return JsonResponse({
            "ticker": ticker,
            "price": str(snapshot.price),
            "source": "snapshot",
            "change_pct": None,
            "previous_close": None,
            "name": ticker,
            "exchange": "",
            "currency": "USD",
        })

    # Fallback 2: deterministic synthetic price — always succeeds
    synth_price, synth_source = get_execution_price(ticker)
    return JsonResponse({
        "ticker": ticker,
        "price": str(synth_price),
        "source": synth_source,
        "change_pct": None,
        "previous_close": None,
        "name": ticker,
        "exchange": "",
        "currency": "USD",
    })


@api_view(["GET"])
def search(request):
    """
    GET /api/market/search/?q=<query>

    Returns matching equity/ETF instruments from Yahoo Finance.
    """
    q = request.query_params.get("q", "").strip()
    if len(q) < 1:
        return JsonResponse([], safe=False)
    results = search_instruments(q)
    return JsonResponse(results, safe=False)


@api_view(["GET"])
def all_prices(request):
    """
    GET /api/market/prices/

    Returns the current simulated price for every tracked symbol.

    Response (200):
    {
      "AAPL": 191.23,
      "TSLA": 178.44,
      ...
    }

    Prices are from the in-memory GBM cache and update every 3 seconds.
    Callers can poll this endpoint to display a live price ticker.
    """
    prices = get_all_prices()
    # Round to 2 dp for clean JSON — internal float precision is 6 dp
    return JsonResponse(
        {symbol: round(price, 2) for symbol, price in sorted(prices.items())},
    )


@api_view(["GET"])
def single_simulated_price(request, ticker: str):
    """
    GET /api/market/simulate/<ticker>/

    Returns the current simulated price for one symbol, initialising it if
    this is the first time it is requested.

    Response (200):
    {
      "symbol": "AAPL",
      "price": 191.23,
      "source": "simulated_live"
    }
    """
    symbol = ticker.strip().upper()
    price = ensure_tracked(symbol)
    return JsonResponse({
        "symbol": symbol,
        "price": round(price, 2),
        "source": "simulated_live",
    })
