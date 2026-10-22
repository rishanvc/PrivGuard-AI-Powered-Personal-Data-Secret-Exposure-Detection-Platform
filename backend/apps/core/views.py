"""Core API views."""

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .health import collect_health


class HealthView(APIView):
    """GET /api/health/ - component status (FR-119, FR-120).

    Explicitly AllowAny. DEFAULT_PERMISSION_CLASSES is IsAuthenticated, so
    every endpoint is locked down unless it opts out here. A health check that
    required a login would be useless for diagnosing a broken login.

    Returns 200 even when degraded: the caller wants the component breakdown,
    and a non-200 would hide it behind DRF's error handler.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(collect_health())
