from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import health
from .views_portfolio import portfolio_summary
from .api import HoldingViewSet

router = DefaultRouter()
router.register("holdings", HoldingViewSet, basename="holding")

urlpatterns = [
    path("health/", health),
    path("portfolio/summary/", portfolio_summary),
    path("", include(router.urls)),
]
