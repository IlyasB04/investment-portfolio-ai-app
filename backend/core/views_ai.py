"""
AI Portfolio Assistant.

Assembles structured portfolio context from the user's live data, then calls
the Claude API to answer user questions in a grounded, portfolio-aware way.

The assistant is deliberately scoped to portfolio analytics — it will not give
general financial advice or promise returns.
"""

import os
from decimal import Decimal

from django.http import JsonResponse
from rest_framework.decorators import api_view

from .market_data import get_quote
from .models import Holding, PortfolioAccount, Transaction
from .views_portfolio import _synthetic_price


# ── Portfolio context assembly ─────────────────────────────────────────────────

def _build_context(user) -> str:
    """
    Return a structured text block describing the user's current portfolio.
    This is injected into the Claude system prompt as factual grounding.
    """
    holdings = list(Holding.objects.filter(user=user).order_by("ticker"))
    account, _ = PortfolioAccount.objects.get_or_create(user=user)

    lines = []

    # ── Holdings ──
    if not holdings:
        lines.append("HOLDINGS: None (empty portfolio)")
    else:
        lines.append("HOLDINGS:")
        total_value = Decimal(0)
        position_rows = []

        for h in holdings:
            quote = get_quote(h.ticker)
            if quote and quote.get("price"):
                price = quote["price"]
                is_synthetic = False
                change_pct = quote.get("change_pct")
            else:
                price = _synthetic_price(h.ticker, h.average_cost)
                is_synthetic = True
                change_pct = None

            market_value = h.quantity * price
            pnl = (price - h.average_cost) * h.quantity
            pnl_pct = float((price - h.average_cost) / h.average_cost * 100)
            total_value += market_value

            position_rows.append({
                "ticker": h.ticker,
                "quantity": float(h.quantity),
                "avg_cost": float(h.average_cost),
                "price": float(price),
                "market_value": float(market_value),
                "pnl": float(pnl),
                "pnl_pct": pnl_pct,
                "is_synthetic": is_synthetic,
                "change_pct": change_pct,
            })

        for row in position_rows:
            price_tag = "(synthetic/estimated)" if row["is_synthetic"] else "(live)"
            day_tag = f", day {row['change_pct']:+.2f}%" if row["change_pct"] is not None else ""
            pnl_sign = "+" if row["pnl"] >= 0 else ""
            lines.append(
                f"  {row['ticker']}: {row['quantity']:.4f} shares, "
                f"avg cost ${row['avg_cost']:.2f}, "
                f"current price ${row['price']:.2f} {price_tag}{day_tag}, "
                f"market value ${row['market_value']:.2f}, "
                f"P&L {pnl_sign}${row['pnl']:.2f} ({pnl_sign}{row['pnl_pct']:.2f}%)"
            )

        # ── Allocation ──
        lines.append("")
        lines.append("ALLOCATION (% of equity):")
        if total_value > 0:
            for row in sorted(position_rows, key=lambda r: r["market_value"], reverse=True):
                pct = row["market_value"] / float(total_value) * 100
                lines.append(f"  {row['ticker']}: {pct:.2f}%")

            # Concentration
            sorted_pcts = sorted(
                [row["market_value"] / float(total_value) * 100 for row in position_rows],
                reverse=True,
            )
            top1 = sorted_pcts[0] if sorted_pcts else 0
            top3 = sum(sorted_pcts[:3])
            lines.append(f"  → Top 1 holding: {top1:.2f}% of equities")
            lines.append(f"  → Top 3 holdings: {top3:.2f}% of equities")

    # ── Cash ──
    lines.append("")
    lines.append(f"CASH BALANCE: ${float(account.cash_balance):.2f}")

    total_with_cash = (
        sum(Decimal(str(r["market_value"])) for r in position_rows)
        + account.cash_balance
        if holdings
        else account.cash_balance
    )
    lines.append(f"TOTAL PORTFOLIO VALUE (equities + cash): ${float(total_with_cash):.2f}")

    # ── Recent transactions (last 10) ──
    txns = Transaction.objects.filter(user=user).order_by("-created_at")[:10]
    if txns:
        lines.append("")
        lines.append("RECENT TRANSACTIONS (newest first):")
        for t in txns:
            lines.append(
                f"  {t.created_at.strftime('%Y-%m-%d')} {t.side} {float(t.quantity):.4f} "
                f"{t.ticker} @ ${float(t.price):.2f} "
                f"(total ${float(t.total_value):.2f}, cash after ${float(t.cash_after):.2f})"
            )
    else:
        lines.append("")
        lines.append("RECENT TRANSACTIONS: None")

    return "\n".join(lines)


_SYSTEM_PROMPT = """You are an AI portfolio assistant for a paper trading platform.
You have access to the user's real portfolio data shown below.
Your role is to help users understand their portfolio — positions, P&L, concentration, cash, and recent activity.

Rules:
- Always base your answers on the portfolio data provided. Do not fabricate figures.
- Be concise and clear. Use numbers from the data directly.
- Do not promise future returns or give investment advice.
- If the user asks about a ticker not in their portfolio, you may comment generally but make clear it is not currently held.
- Use plain language. Avoid jargon unless the user introduces it.
- If the portfolio is empty, say so and suggest they add positions or import a CSV.

PORTFOLIO DATA (as of this request):
{context}
"""


# ── Claude call ────────────────────────────────────────────────────────────────

def _call_claude(question: str, context: str) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return (
            "The AI assistant is not configured. "
            "Set ANTHROPIC_API_KEY in the backend .env file to enable it."
        )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=_SYSTEM_PROMPT.format(context=context),
            messages=[{"role": "user", "content": question}],
        )
        return message.content[0].text
    except Exception as exc:
        return f"AI assistant error: {exc}"


# ── View ───────────────────────────────────────────────────────────────────────

@api_view(["POST"])
def portfolio_chat(request):
    """
    POST /api/ai/chat/

    Body: { "message": "What is my largest holding?" }
    Returns: { "response": "...", "context_summary": "..." }
    """
    message = request.data.get("message", "").strip()
    if not message:
        return JsonResponse({"error": "message is required."}, status=400)
    if len(message) > 2000:
        return JsonResponse({"error": "message too long (max 2000 chars)."}, status=400)

    context = _build_context(request.user)
    response = _call_claude(message, context)

    # Return a brief context summary so the frontend can show what data was used
    holdings_count = Holding.objects.filter(user=request.user).count()
    context_summary = f"Based on {holdings_count} position{'s' if holdings_count != 1 else ''} and recent transactions"

    return JsonResponse({"response": response, "context_summary": context_summary})
