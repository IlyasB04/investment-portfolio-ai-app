import hashlib
from decimal import Decimal

from django.http import JsonResponse
from rest_framework.decorators import api_view

from .models import Holding, PriceSnapshot

_SYNTHETIC_MIN = Decimal("0.85")
_SYNTHETIC_RANGE = Decimal("0.50")  # 0.85 + 0.50 = 1.35 max


def _synthetic_price(ticker: str, average_cost: Decimal) -> Decimal:
    """
    Return a deterministic synthetic price derived from the ticker and average_cost.

    Method: SHA-256 the uppercased ticker, take the first 8 hex digits as an
    unsigned integer, normalise to [0, 1) by dividing by 0xFFFFFFFF, then scale
    into [0.85, 1.35].  The result is stable between requests because the hash
    of a given ticker string never changes.
    """
    digest = hashlib.sha256(ticker.upper().encode()).hexdigest()
    seed = int(digest[:8], 16)
    ratio = Decimal(seed) / Decimal(0xFFFFFFFF)
    multiplier = _SYNTHETIC_MIN + ratio * _SYNTHETIC_RANGE
    return (average_cost * multiplier).quantize(Decimal("0.000001"))


@api_view(["GET"])
def portfolio_summary(request):
    holdings = list(Holding.objects.filter(user=request.user))

    tickers = {h.ticker for h in holdings}
    latest_prices = {}
    for ticker in tickers:
        snapshot = PriceSnapshot.objects.filter(ticker=ticker).order_by("-as_of").first()
        if snapshot:
            latest_prices[ticker] = snapshot.price

    positions = []
    for h in holdings:
        real_price = latest_prices.get(h.ticker)
        if real_price is not None:
            price = real_price
            is_synthetic = False
        else:
            price = _synthetic_price(h.ticker, h.average_cost)
            is_synthetic = True
        market_value = h.quantity * price
        pnl = (price - h.average_cost) * h.quantity
        positions.append({
            "id": h.id,
            "ticker": h.ticker,
            "quantity": str(h.quantity),
            "average_cost": str(h.average_cost),
            "price": str(price),
            "market_value": str(market_value),
            "pnl": str(pnl),
            "is_synthetic_price": is_synthetic,
        })

    total_value = sum(
        (Decimal(p["market_value"]) for p in positions),
        Decimal(0),
    )

    allocation = []
    if total_value > 0:
        for p in positions:
            pct = Decimal(p["market_value"]) / total_value * 100
            allocation.append({
                "ticker": p["ticker"],
                "market_value": p["market_value"],
                "percent_of_portfolio": str(round(pct, 6)),
            })
        allocation.sort(key=lambda x: Decimal(x["percent_of_portfolio"]), reverse=True)

    percents = [float(a["percent_of_portfolio"]) for a in allocation]
    top1 = percents[0] if percents else 0.0
    top3 = sum(percents[:3])

    return JsonResponse({
        "total_value": str(total_value),
        "positions": positions,
        "allocation": allocation,
        "concentration": {
            "top1_percent": round(top1, 6),
            "top3_percent": round(top3, 6),
        },
    })
