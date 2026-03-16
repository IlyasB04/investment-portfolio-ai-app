"""
Paper trading order execution.

Market orders only. Execution price = latest available quote.
Cash and holdings are updated atomically via a database transaction.
"""

from decimal import Decimal

from django.db import transaction as db_transaction
from django.http import JsonResponse
from rest_framework.decorators import api_view
from rest_framework.request import Request

from .market_data import get_quote
from .models import AuditEvent, Holding, Order, PortfolioAccount, Transaction
from .views_portfolio import _synthetic_price


def _get_account(user) -> PortfolioAccount:
    account, _ = PortfolioAccount.objects.get_or_create(user=user)
    return account


def _get_execution_price(ticker: str, average_cost: Decimal | None) -> tuple[Decimal, str]:
    """Return (price, source) using live quote → snapshot → synthetic fallback."""
    live = get_quote(ticker)
    if live:
        return live["price"], "live"

    from .models import PriceSnapshot
    snap = PriceSnapshot.objects.filter(ticker=ticker).order_by("-as_of").first()
    if snap:
        return snap.price, "snapshot"

    if average_cost:
        return _synthetic_price(ticker, average_cost), "synthetic"

    raise ValueError(f"No price available for {ticker}")


@api_view(["POST"])
def place_order(request: Request):
    """
    POST /api/orders/

    Body: { side: "BUY"|"SELL", ticker: str, quantity: number }

    BUY:  deducts cash, creates/aggregates holding.
    SELL: validates quantity, reduces holding, adds cash.
    """
    side = request.data.get("side", "").upper()
    ticker = request.data.get("ticker", "").strip().upper()
    try:
        quantity = Decimal(str(request.data.get("quantity", 0)))
    except Exception:
        return JsonResponse({"error": "Invalid quantity."}, status=400)

    if side not in ("BUY", "SELL"):
        return JsonResponse({"error": "side must be BUY or SELL."}, status=400)
    if not ticker:
        return JsonResponse({"error": "ticker is required."}, status=400)
    if quantity <= 0:
        return JsonResponse({"error": "quantity must be positive."}, status=400)

    with db_transaction.atomic():
        account = _get_account(request.user)

        # Determine execution price
        existing_holding = Holding.objects.filter(
            user=request.user, ticker__iexact=ticker
        ).first()
        avg_cost_hint = existing_holding.average_cost if existing_holding else None

        try:
            exec_price, price_source = _get_execution_price(ticker, avg_cost_hint)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)

        total_value = (exec_price * quantity).quantize(Decimal("0.01"))

        if side == "BUY":
            if account.cash_balance < total_value:
                return JsonResponse(
                    {"error": f"Insufficient cash. Available: ${account.cash_balance}, required: ${total_value}."},
                    status=400,
                )
            account.cash_balance -= total_value
            account.save()

            # Aggregate or create holding
            if existing_holding:
                new_qty = existing_holding.quantity + quantity
                new_avg = (existing_holding.quantity * existing_holding.average_cost + quantity * exec_price) / new_qty
                existing_holding.quantity = new_qty
                existing_holding.average_cost = new_avg
                existing_holding.save()
                holding = existing_holding
            else:
                holding = Holding.objects.create(
                    user=request.user,
                    ticker=ticker,
                    quantity=quantity,
                    average_cost=exec_price,
                )

        else:  # SELL
            if not existing_holding or existing_holding.quantity < quantity:
                available = existing_holding.quantity if existing_holding else Decimal(0)
                return JsonResponse(
                    {"error": f"Insufficient holdings. Available: {available} {ticker}."},
                    status=400,
                )
            account.cash_balance += total_value
            account.save()

            existing_holding.quantity -= quantity
            if existing_holding.quantity == 0:
                existing_holding.delete()
                holding = None
            else:
                existing_holding.save()
                holding = existing_holding

        # Record order and transaction
        order = Order.objects.create(
            user=request.user,
            ticker=ticker,
            side=side,
            quantity=quantity,
            executed_price=exec_price,
            total_value=total_value,
            status=Order.Status.FILLED,
        )
        Transaction.objects.create(
            user=request.user,
            order=order,
            ticker=ticker,
            side=side,
            quantity=quantity,
            price=exec_price,
            total_value=total_value,
            cash_after=account.cash_balance,
        )
        AuditEvent.objects.create(
            user=request.user,
            event_type=f"order_{side.lower()}",
            description=f"{side} {quantity} {ticker} @ {exec_price} (source: {price_source}). Cash after: {account.cash_balance}",
        )

    return JsonResponse({
        "status": "filled",
        "side": side,
        "ticker": ticker,
        "quantity": str(quantity),
        "executed_price": str(exec_price),
        "total_value": str(total_value),
        "cash_balance": str(account.cash_balance),
        "price_source": price_source,
    }, status=201)


@api_view(["GET"])
def recent_transactions(request):
    """
    GET /api/orders/transactions/?limit=20

    Returns recent transactions for the current user.
    """
    limit = min(int(request.query_params.get("limit", 20)), 100)
    txns = (
        Transaction.objects.filter(user=request.user)
        .order_by("-created_at")[:limit]
    )
    return JsonResponse([
        {
            "id": t.id,
            "ticker": t.ticker,
            "side": t.side,
            "quantity": str(t.quantity),
            "price": str(t.price),
            "total_value": str(t.total_value),
            "cash_after": str(t.cash_after),
            "created_at": t.created_at.isoformat(),
        }
        for t in txns
    ], safe=False)
