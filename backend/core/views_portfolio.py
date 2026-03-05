from decimal import Decimal

from django.http import JsonResponse
from rest_framework.decorators import api_view

from .models import Holding, PriceSnapshot


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
        price = latest_prices.get(h.ticker)
        if price is not None:
            market_value = h.quantity * price
            pnl = (price - h.average_cost) * h.quantity
        else:
            market_value = None
            pnl = None
        positions.append({
            "ticker": h.ticker,
            "quantity": str(h.quantity),
            "average_cost": str(h.average_cost),
            "price": str(price) if price is not None else None,
            "market_value": str(market_value) if market_value is not None else None,
            "pnl": str(pnl) if pnl is not None else None,
        })

    total_value = sum(
        (Decimal(p["market_value"]) for p in positions if p["market_value"] is not None),
        Decimal(0),
    )

    allocation = []
    if total_value > 0:
        for p in positions:
            if p["market_value"] is not None:
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
