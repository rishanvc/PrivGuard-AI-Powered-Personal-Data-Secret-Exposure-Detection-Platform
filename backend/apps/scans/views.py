"""Scan API (SRS 11): /api/scans/... and /api/dashboard/."""

from django.conf import settings
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsOwner, OwnedQuerysetMixin
from privguard_engine.intake import supported_extensions

from . import services
from .models import Scan
from .serializers import (
    FindingSerializer,
    ScanCreateSerializer,
    ScanDetailSerializer,
    ScanListSerializer,
    ScannedFileSerializer,
)


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with the scan's current state."
    default_code = "conflict"


class StorageFailure(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Stored files could not be removed."
    default_code = "storage_failure"


class FilePagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 200


class FindingPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class ScanViewSet(
    OwnedQuerysetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Every object lookup goes through OwnedQuerysetMixin.get_queryset, so
    another user's scan is simply not found - 404 for retrieve, files, start,
    cancel and delete alike (FR-005, NFR-018)."""

    queryset = Scan.objects.all()
    permission_classes = [IsAuthenticated, IsOwner]

    def get_serializer_class(self):
        return ScanListSerializer if self.action == "list" else ScanDetailSerializer

    def create(self, request):
        serializer = ScanCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        scan = services.create_scan(
            user=request.user,
            name=serializer.validated_data["name"],
            scan_type=serializer.validated_data["scan_type"],
            files=serializer.incoming_files(),
        )
        return Response(ScanDetailSerializer(scan).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        try:
            services.delete_scan(instance)
        except services.ScanStateError as exc:
            raise Conflict(str(exc))
        except services.ScanStorageError as exc:
            raise StorageFailure(str(exc))

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        return self._transition("start")

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._transition("cancel")

    def _transition(self, name):
        scan = self.get_object()  # 404 unless it's the caller's scan
        try:
            scan = services.transition(scan, name)
        except services.ScanStateError as exc:
            raise Conflict(str(exc))
        return Response(ScanDetailSerializer(scan).data)

    @action(detail=True, methods=["get"])
    def files(self, request, pk=None):
        scan = self.get_object()
        queryset = scan.files.select_related("duplicate_of").order_by("relative_path", "created_at")
        paginator = FilePagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(ScannedFileSerializer(page, many=True).data)

    @action(detail=True, methods=["get"])
    def findings(self, request, pk=None):
        """Most confident first. Search, filters and review arrive in Cycle 7."""
        scan = self.get_object()  # 404 unless it's the caller's scan
        queryset = scan.findings.select_related("scanned_file").order_by(
            "-confidence", "scanned_file__relative_path", "subcategory", "created_at", "id"
        )
        paginator = FindingPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(FindingSerializer(page, many=True).data)

    @action(detail=False, methods=["get"])
    def limits(self, request):
        """The server's real limits, so the UI can warn before uploading."""
        return Response({
            "max_file_mb": settings.MAX_UPLOAD_SIZE_MB,
            "max_total_mb": settings.MAX_TOTAL_SCAN_SIZE_MB,
            "max_files": settings.MAX_FILES_PER_SCAN,
            "supported_extensions": supported_extensions(),
        })


class DashboardView(APIView):
    """GET /api/dashboard/ - the caller's own totals (FR-081)."""

    def get(self, request):
        return Response(services.dashboard_summary(request.user))
