"""
Market Intelligence view.

GET /api/market-intelligence/

Returns a single JSON payload:
  timestamp       — ISO 8601 UTC fetch time
  market_pulse    — overall sentiment + counts + top themes
  headlines       — enriched list (sentiment, themes, tickers)
  holdings_impact — per-ticker impact with explanation
  sector_impact   — per-sector impact with explanation
  ai_summary      — Groq-generated 3-sentence summary (or null)
  ai_error        — error code if AI call failed (or null)
  sources_used    — RSS sources that responded
  no_data         — true if no headlines were fetched
"""

import logging

from django.http import JsonResponse
from rest_framework.decorators import api_view

logger = logging.getLogger(__name__)


@api_view(["GET"])
def market_intelligence(request):
    """
    GET /api/market-intelligence/

    Fetches live finance headlines, analyses sentiment and themes,
    maps results to the authenticated user's holdings, and returns
    a structured intelligence report.

    No request parameters are required — holdings are loaded from
    the authenticated user's portfolio automatically.
    """
    try:
        from .services.market_intelligence import get_market_intelligence
        data = get_market_intelligence(request.user)
        return JsonResponse(data)
    except Exception as exc:
        logger.exception("[market_intelligence] unexpected error: %s", exc)
        return JsonResponse(
            {"error": "Failed to fetch market intelligence. Please try again."},
            status=500,
        )
