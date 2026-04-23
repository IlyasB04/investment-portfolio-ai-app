from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api import HoldingViewSet
from .views import health
from .views_import import import_csv
from .views_market import all_prices, quote, search, single_simulated_price
from .views_portfolio import portfolio_history, portfolio_summary
from .views_ai import (
    ai_health,
    ai_history,
    create_conversation,
    list_conversations,
    conversation_detail,
    intelligence_chat,
    portfolio_chat,
    financial_chat,
)
from .views_trading import place_order, recent_transactions
from .views_market_intelligence import market_intelligence

router = DefaultRouter()
router.register("holdings", HoldingViewSet, basename="holding")

urlpatterns = [
    path("health/", health),

    # Portfolio
    path("portfolio/summary/", portfolio_summary),
    path("portfolio/history/", portfolio_history),
    path("portfolio/import/", import_csv),

    # Market data
    path("market/quote/<str:ticker>/", quote),
    path("market/search/", search),
    path("market/prices/", all_prices),
    path("market/simulate/<str:ticker>/", single_simulated_price),

    # Market Intelligence
    path("market-intelligence/", market_intelligence),

    # Paper trading
    path("orders/", place_order),
    path("orders/transactions/", recent_transactions),

    # AI assistant — multi-conversation system
    path("ai/health/", ai_health),
    path("ai/conversations/", list_conversations),
    path("ai/conversations/new/", create_conversation),
    path("ai/conversations/<str:conversation_id>/messages/", conversation_detail),
    path("ai/intelligence/", intelligence_chat),

    # Legacy endpoints (backward compat)
    path("ai/history/", ai_history),
    path("ai/chat/", portfolio_chat),
    path("ai/financial-chat/", financial_chat),

    # Holdings CRUD (router)
    path("", include(router.urls)),
]
