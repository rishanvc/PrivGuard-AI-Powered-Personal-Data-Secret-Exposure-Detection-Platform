"""Scan routes, mounted at /api/."""

from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import DashboardView, FindingViewSet, ScanViewSet

router = SimpleRouter()
router.register("scans", ScanViewSet, basename="scan")
router.register("findings", FindingViewSet, basename="finding")

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    *router.urls,
]
