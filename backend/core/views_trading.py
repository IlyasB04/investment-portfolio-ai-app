"""
Paper trading order execution.

Market orders only.  Execution price is resolved via:
  1. Yahoo Finance live quote
  2. Latest PriceSnapshot in DB
  3. Deterministic synthetic price  (ALWAYS succeeds)

Cash and holdings are updated atomically inside a DB transaction.
The endpoint NEVER returns a silent failure — every error path returns a
structured JSON error body with an "error" key.
"""

import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction as db_transaction
from django.http import JsonResponse
from rest_framework.decorators import api_view
from rest_framework.request import Request

from .market_data import get_execution_price
from .models import AuditEvent, Holding, Order, PortfolioAccount, Transaction

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_account(user) -> PortfolioAccount:
    account, created = PortfolioAccount.objects.get_or_create(user=user)
    if created:
        logger.info("Created PortfolioAccount for user %s with default cash balance", user.id)
    return account


def _parse_quantity(raw) -> tuple[Decimal | None, str | None]:
    """Parse and validate quantity from request data. Returns (value, error_msg)."""
    try:
        qty = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return None, "quantity must be a valid number."
    if qty <= 0:
        return None, "quantity must be greater than zero."
    if qty > Decimal("1_000_000"):
        return None, "quantity exceeds maximum order size of 1,000,000."
    return qty, None


# ── Order endpoint ─────────────────────────────────────────────────────────────

@api_view(["POST"])
def place_order(request: Request):
    """
    POST /api/orders/

    Request body
    ------------
    {
      "side":     "BUY" | "SELL",
      "ticker":   str,
      "quantity": number
    }

    Success response (201)
    ----------------------
    {
      "status":          "filled",
      "side":            "BUY" | "SELL",
      "ticker":          str,
      "quantity":        str,
      "executed_price":  str,
      "total_value":     str,
      "cash_balance":    str,
      "price_source":    "live" | "snapshot" | "synthetic"
    }

    Error response (400)
    --------------------
    { "error": "human-readable message" }
    """
    # ── Input validation ────────────────────────────────────────────────────────
    side = str(request.data.get("side", "")).strip().upper()
    ticker = str(request.data.get("ticker", "")).strip().upper()
    raw_qty = request.data.get("quantity", 0)

    if side not in ("BUY", "SELL"):
        return JsonResponse({"error": "side must be BUY or SELL."}, status=400)
    if not ticker:
        return JsonResponse({"error": "ticker is required."}, status=400)
    if len(ticker) > 20:
        return JsonResponse({"error": "ticker symbol is too long."}, status=400)

    quantity, qty_error = _parse_quantity(raw_qty)
    if qty_error:
        return JsonResponse({"error": qty_error}, status=400)

    # ── Atomic execution ────────────────────────────────────────────────────────
    try:
        with db_transaction.atomic():
            account = _get_account(request.user)

            # Resolve price — this NEVER raises thanks to synthetic fallback
            existing_holding = (
                Holding.objects.filter(user=request.user, ticker__iexact=ticker)
                .select_for_update()
                .first()
            )
            avg_cost_hint = existing_holding.average_cost if existing_holding else None

            exec_price, price_source = get_execution_price(ticker, avg_cost_hint)
            total_value = (exec_price * quantity).quantize(Decimal("0.01"))

            logger.info(
                "Order attempt: user=%s side=%s ticker=%s qty=%s price=%s source=%s",
                request.user.id, side, ticker, quantity, exec_price, price_source,
            )

            if side == "BUY":
                if account.cash_balance < total_value:
                    return JsonResponse(
                        {
                            "error": (
                                f"Insufficient cash. "
                                f"Available: ${account.cash_balance:,.2f}, "
                                f"required: ${total_value:,.2f}."
                            )
                        },
                        status=400,
                    )
                account.cash_balance -= total_value
                account.save(update_fields=["cash_balance"])

                if existing_holding:
                    new_qty = existing_holding.quantity + quantity
                    new_avg = (
                        existing_holding.quantity * existing_holding.average_cost
                        + quantity * exec_price
                    ) / new_qty
                    existing_holding.quantity = new_qty
                    existing_holding.average_cost = new_avg.quantize(Decimal("0.0001"))
                    existing_holding.save(update_fields=["quantity", "average_cost"])
                    holding = existing_holding
                else:
                    holding = Holding.objects.create(
                        user=request.user,
                        ticker=ticker,
                        quantity=quantity,
                        average_cost=exec_price.quantize(Decimal("0.0001")),
                    )

            else:  # SELL
                available = existing_holding.quantity if existing_holding else Decimal(0)
                if not existing_holding or available < quantity:
                    return JsonResponse(
                        {
                            "error": (
                                f"Insufficient holdings. "
                                f"You hold {available:f} {ticker}, "
                                f"tried to sell {quantity:f}."
                            )
                        },
                        status=400,
                    )
                account.cash_balance += total_value
                account.save(update_fields=["cash_balance"])

                existing_holding.quantity -= quantity
                if existing_holding.quantity <= Decimal("0.000001"):
                    existing_holding.delete()
                    holding = None
                else:
                    existing_holding.save(update_fields=["quantity"])
                    holding = existing_holding

            # Record order + transaction
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
                description=(
                    f"{side} {quantity} {ticker} @ {exec_price} "
                    f"(source: {price_source}). "
                    f"Cash after: {account.cash_balance}"
                ),
            )

            logger.info(
                "Order filled: user=%s side=%s ticker=%s qty=%s price=%s cash_after=%s",
                request.user.id, side, ticker, quantity, exec_price, account.cash_balance,
            )

    except Exception as exc:
        logger.exception(
            "Unexpected error placing order: user=%s side=%s ticker=%s qty=%s",
            request.user.id, side, ticker, raw_qty,
        )
        return JsonResponse(
            {"error": "An unexpected error occurred. Please try again."},
            status=500,
        )

    return JsonResponse(
        {
            "status": "filled",
            "side": side,
            "ticker": ticker,
            "quantity": str(quantity),
            "executed_price": str(exec_price),
            "total_value": str(total_value),
            "cash_balance": str(account.cash_balance),
            "price_source": price_source,
        },
        status=201,
    )


# ── Transactions endpoint ──────────────────────────────────────────────────────

@api_view(["GET"])
def recent_transactions(request: Request):
    """
    GET /api/orders/transactions/?limit=20

    Returns up to 100 recent transactions for the authenticated user.
    """
    try:
        limit = max(1, min(int(request.query_params.get("limit", 20)), 100))
    except (ValueError, TypeError):
        limit = 20

    txns = (
        Transaction.objects.filter(user=request.user)
        .select_related("order")
        .order_by("-created_at")[:limit]
    )

    return JsonResponse(
        [
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
        ],
        safe=False,
    )
