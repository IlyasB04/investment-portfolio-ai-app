"""
Portfolio analytics views.

portfolio_summary — full snapshot of positions with current pricing.
portfolio_history — 30-day synthetic history built from current value.

Price resolution per position:
  0. GBM simulator  (in-memory, always current — fastest path, no I/O)
  1. Yahoo Finance live quote  (parallel fetch per ticker — fallback only)
  2. Latest PriceSnapshot in DB
  3. Deterministic synthetic price (always succeeds)
"""

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from decimal import Decimal

from django.http import JsonResponse
from rest_framework.decorators import api_view

from .market_data import get_quote
from .models import Holding, PortfolioAccount, PriceSnapshot

logger = logging.getLogger(__name__)

_HISTORY_DAYS = 30
_MOVE_HALF = Decimal("0.02")   # movement range: [-2%, +2%]
_MAX_QUOTE_WORKERS = 6         # parallel live-quote fetches

_SYNTHETIC_MIN = Decimal("0.85")
_SYNTHETIC_RANGE = Decimal("0.50")  # [0.85, 1.35]


# ── Internal helpers ───────────────────────────────────────────────────────────

def _day_movement(user_id: int, d: date) -> Decimal:
    """
    Deterministic daily return for a given user and date.
    SHA-256("{user_id}:{YYYY-MM-DD}") → first 8 hex digits → [-2%, +2%).
    """
    key = f"{user_id}:{d.isoformat()}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    seed = int(digest[:8], 16)
    ratio = Decimal(seed) / Decimal(0xFFFF_FFFF)
    return ratio * (_MOVE_HALF * 2) - _MOVE_HALF


def _synthetic_price(ticker: str, average_cost: Decimal) -> Decimal:
    """Deterministic synthetic price in [0.85 × avg_cost, 1.35 × avg_cost]."""
    digest = hashlib.sha256(ticker.upper().encode()).hexdigest()
    seed = int(digest[:8], 16)
    ratio = Decimal(seed) / Decimal(0xFFFF_FFFF)
    multiplier = _SYNTHETIC_MIN + ratio * _SYNTHETIC_RANGE
    return (average_cost * multiplier).quantize(Decimal("0.0001"))


def _resolve_price(ticker: str, average_cost: Decimal) -> tuple[Decimal, bool]:
    """
    Return (price, is_synthetic).

    Resolution order:
      0. GBM simulator  (in-memory, no I/O, always current)
      1. Yahoo Finance live quote
      2. Latest PriceSnapshot in DB
      3. Deterministic synthetic fallback
    """
    # 0. GBM simulator — O(1), no network or DB call
    try:
        from .simulator import ensure_tracked
        sim_price = ensure_tracked(ticker)
        if sim_price and sim_price > 0:
            return Decimal(str(round(sim_price, 4))).quantize(Decimal("0.0001")), False
    except Exception as exc:
        logger.debug("Simulator price unavailable for %s: %s", ticker, exc)

    # 1. Yahoo Finance live (fallback — slower, requires network)
    try:
        live = get_quote(ticker)
        if live and live.get("price") and live["price"] > 0:
            return live["price"], False
    except Exception as exc:
        logger.debug("Live quote failed for %s: %s", ticker, exc)

    # 2. Latest PriceSnapshot from DB
    try:
        snap = PriceSnapshot.objects.filter(ticker=ticker).order_by("-as_of").first()
        if snap and snap.price > 0:
            return snap.price, False
    except Exception as exc:
        logger.debug("Snapshot lookup failed for %s: %s", ticker, exc)

    # 3. Deterministic synthetic — always succeeds
    return _synthetic_price(ticker, average_cost), True


def _fetch_prices_parallel(holdings: list) -> dict[str, tuple[Decimal, bool]]:
    """Fetch current prices for all tickers in parallel threads."""
    results: dict[str, tuple[Decimal, bool]] = {}
    if not holdings:
        return results

    avg_costs = {h.ticker: h.average_cost for h in holdings}
    tickers = list(avg_costs.keys())

    with ThreadPoolExecutor(max_workers=min(_MAX_QUOTE_WORKERS, len(tickers))) as pool:
        future_map = {
            pool.submit(_resolve_price, t, avg_costs[t]): t
            for t in tickers
        }
        for future in as_completed(future_map):
            ticker = future_map[future]
            try:
                results[ticker] = future.result()
            except Exception as exc:
                logger.warning("Price resolution failed for %s: %s", ticker, exc)
                results[ticker] = (_synthetic_price(ticker, avg_costs[ticker]), True)

    return results


# ── Views ──────────────────────────────────────────────────────────────────────

@api_view(["GET"])
def portfolio_summary(request):
    """GET /api/portfolio/summary/ — full portfolio snapshot with live pricing."""
    holdings = list(Holding.objects.filter(user=request.user))
    prices = _fetch_prices_parallel(holdings)

    positions = []
    for h in holdings:
        price, is_synthetic = prices.get(
            h.ticker, (_synthetic_price(h.ticker, h.average_cost), True)
        )
        market_value = (h.quantity * price).quantize(Decimal("0.01"))
        pnl = ((price - h.average_cost) * h.quantity).quantize(Decimal("0.01"))
        positions.append({
            "id": h.id,
            "ticker": h.ticker,
            "quantity": str(h.quantity),
            "average_cost": str(h.average_cost),
            "price": str(price.quantize(Decimal("0.0001"))),
            "market_value": str(market_value),
            "pnl": str(pnl),
            "is_synthetic_price": is_synthetic,
        })

    total_value = sum(Decimal(p["market_value"]) for p in positions)

    allocation = []
    if total_value > 0:
        for p in positions:
            pct = Decimal(p["market_value"]) / total_value * 100
            allocation.append({
                "ticker": p["ticker"],
                "market_value": p["market_value"],
                "percent_of_portfolio": str(round(pct, 4)),
            })
        allocation.sort(key=lambda x: Decimal(x["percent_of_portfolio"]), reverse=True)

    percents = [float(a["percent_of_portfolio"]) for a in allocation]
    top1 = percents[0] if percents else 0.0
    top3 = sum(percents[:3])

    account, _ = PortfolioAccount.objects.get_or_create(user=request.user)
    total_with_cash = (total_value + account.cash_balance).quantize(Decimal("0.01"))

    return JsonResponse({
        "total_value": str(total_value.quantize(Decimal("0.01"))),
        "cash_balance": str(account.cash_balance.quantize(Decimal("0.01"))),
        "total_with_cash": str(total_with_cash),
        "positions": positions,
        "allocation": allocation,
        "concentration": {
            "top1_percent": round(top1, 4),
            "top3_percent": round(top3, 4),
        },
    })


@api_view(["GET"])
def portfolio_history(request):
    """GET /api/portfolio/history/ — 30-day synthetic history ending today."""
    holdings = list(Holding.objects.filter(user=request.user))
    prices = _fetch_prices_parallel(holdings)

    current_value = sum(
        h.quantity * prices.get(h.ticker, (_synthetic_price(h.ticker, h.average_cost), True))[0]
        for h in holdings
    ) if holdings else Decimal(0)

    today = date.today()
    points = []
    value = current_value

    for offset in range(_HISTORY_DAYS):
        d = today - timedelta(days=offset)
        points.append({
            "date": d.isoformat(),
            "value": float(value.quantize(Decimal("0.01"))),
        })
        if offset < _HISTORY_DAYS - 1:
            movement = _day_movement(request.user.id, d)
            value = value / (1 + movement)

    points.reverse()
    return JsonResponse(points, safe=False)
