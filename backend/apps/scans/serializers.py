"""Serializers for scans and their file inventory."""

from django.conf import settings
from django.db.models import Count
from rest_framework import serializers

from . import lifecycle
from .models import Scan, ScannedFile
from .services import IncomingFile


class ScanListSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Scan
        fields = [
            "id", "name", "scan_type", "status", "status_display",
            "total_files", "total_findings", "created_at",
        ]
        read_only_fields = fields


class ScanDetailSerializer(ScanListSerializer):
    file_counts = serializers.SerializerMethodField()
    actions = serializers.SerializerMethodField()

    class Meta(ScanListSerializer.Meta):
        fields = ScanListSerializer.Meta.fields + [
            "processed_files", "failed_files", "risk_score", "configuration", "error_summary",
            "started_at", "completed_at", "updated_at", "file_counts", "actions",
        ]
        read_only_fields = fields

    def get_file_counts(self, scan):
        counts = {status: 0 for status in ScannedFile.Status.values}
        for row in scan.files.order_by().values("processing_status").annotate(n=Count("id")):
            counts[row["processing_status"]] = row["n"]
        return counts

    def get_actions(self, scan):
        """Which buttons the UI should offer. The server re-checks every request anyway."""
        can_start = lifecycle.can("start", scan.status) and scan.files.filter(
            processing_status=ScannedFile.Status.PENDING
        ).exists()
        return {
            "start": can_start,
            "cancel": lifecycle.can("cancel", scan.status),
            "delete": scan.status not in lifecycle.UNDELETABLE,
        }


class ScannedFileSerializer(serializers.ModelSerializer):
    """One inventory row. The storage location and hash stay server-side."""

    status = serializers.CharField(source="processing_status", read_only=True)
    status_display = serializers.CharField(source="get_processing_status_display", read_only=True)
    reason = serializers.CharField(source="error_summary", read_only=True)
    duplicate_of_path = serializers.CharField(
        source="duplicate_of.relative_path", default=None, read_only=True
    )

    class Meta:
        model = ScannedFile
        fields = [
            "id", "file_name", "relative_path", "file_type", "file_size", "status",
            "status_display", "reason", "extraction_status", "duplicate_of_path", "created_at",
        ]
        read_only_fields = fields


class ScanCreateSerializer(serializers.Serializer):
    """Multipart body for POST /api/scans/.

    Folder uploads send one `paths` entry per file, in the same order, because
    Django keeps only the base name of an uploaded file's name for safety.
    """

    name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    scan_type = serializers.ChoiceField(
        choices=[(Scan.ScanType.FILES, "Files"), (Scan.ScanType.FOLDER, "Folder")]
    )
    # allow_empty_file: an empty file is inventoried as "skipped", not refused.
    files = serializers.ListField(
        child=serializers.FileField(allow_empty_file=True), allow_empty=False
    )
    paths = serializers.ListField(
        child=serializers.CharField(max_length=2048, trim_whitespace=False),
        required=False,
        default=list,
    )

    def validate_files(self, files):
        if len(files) > settings.MAX_FILES_PER_SCAN:
            raise serializers.ValidationError(
                f"Too many files. One scan can contain at most {settings.MAX_FILES_PER_SCAN} files."
            )
        return files

    def validate(self, attrs):
        files, paths = attrs["files"], attrs["paths"]
        if attrs["scan_type"] == Scan.ScanType.FOLDER:
            if len(paths) != len(files):
                raise serializers.ValidationError(
                    {"paths": "A folder upload needs exactly one relative path per file."}
                )
        elif paths:
            raise serializers.ValidationError(
                {"paths": "Relative paths are only accepted for folder uploads."}
            )
        return attrs

    def incoming_files(self) -> list[IncomingFile]:
        data = self.validated_data
        if data["scan_type"] == Scan.ScanType.FOLDER:
            return [IncomingFile(f, p) for f, p in zip(data["files"], data["paths"])]
        return [IncomingFile(f) for f in data["files"]]
