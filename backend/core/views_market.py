from django.http import JsonResponse
from rest_framework.decorators import api_view

from .market_data import get_quote, search_instruments
from .models import PriceSnapshot
from .views_portfolio import _synthetic_price


@api_view(["GET"])
def quote(request, ticker: str):
    """
    GET /api/market/quote/<ticker>/

    Returns live quote from Yahoo Finance.
    Falls back to latest PriceSnapshot, then deterministic synthetic price.
    """
    ticker = ticker.strip().upper()
    live = get_quote(ticker)

    if live:
        return JsonResponse({**live, "price": str(live["price"]), "previous_close": str(live["previous_close"]) if live["previous_close"] else None, "source": "live"})

    # Fallback 1: stored snapshot
    snapshot = PriceSnapshot.objects.filter(ticker=ticker).order_by("-as_of").first()
    if snapshot:
        return JsonResponse({"ticker": ticker, "price": str(snapshot.price), "source": "snapshot", "change_pct": None, "previous_close": None, "name": ticker, "exchange": "", "currency": "USD"})

    # Fallback 2: synthetic — needs average_cost; return placeholder so frontend knows
    return JsonResponse({"ticker": ticker, "price": None, "source": "unavailable", "change_pct": None, "previous_close": None, "name": ticker, "exchange": "", "currency": "USD"}, status=200)


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
