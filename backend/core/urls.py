from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api import HoldingViewSet
from .views import health
from .views_import import import_csv
from .views_market import quote, search
from .views_portfolio import portfolio_history, portfolio_summary
from .views_trading import place_order, recent_transactions

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

    # Paper trading
    path("orders/", place_order),
    path("orders/transactions/", recent_transactions),

    # Holdings CRUD (router)
    path("", include(router.urls)),
]
