"""Serializers for scans and their file inventory."""

from django.conf import settings
from django.db.models import Count
from rest_framework import serializers

from privguard_engine.detectors import TYPE_LABELS
from privguard_engine.risk import BANDS, LEVELS, RISK_POLICY_VERSION, band

from apps.audit.models import AuditLog

from . import lifecycle
from .models import Finding, Scan, ScannedFile
from .services import REVIEW_ACTION, IncomingFile, compute_scan_risk

FS = ScannedFile.Status
PROCESSED = (FS.COMPLETED, FS.FAILED)
ACCEPTED = (FS.PENDING, FS.PROCESSING, FS.COMPLETED, FS.FAILED)  # everything the worker handles


class ScanListSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    risk_band = serializers.SerializerMethodField()

    class Meta:
        model = Scan
        fields = [
            "id", "name", "scan_type", "status", "status_display",
            "total_files", "total_findings", "risk_score", "risk_band", "created_at",
        ]
        read_only_fields = fields

    def get_risk_band(self, scan):
        """FR-077: "low" | "moderate" | "high" | "critical", or None while not scored."""
        return None if scan.risk_score is None else band(scan.risk_score)[0]


class ScanDetailSerializer(ScanListSerializer):
    file_counts = serializers.SerializerMethodField()
    extraction_counts = serializers.SerializerMethodField()
    finding_counts = serializers.SerializerMethodField()
    severity_counts = serializers.SerializerMethodField()
    risk = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    actions = serializers.SerializerMethodField()

    class Meta(ScanListSerializer.Meta):
        fields = ScanListSerializer.Meta.fields + [
            "processed_files", "failed_files", "configuration", "error_summary",
            "started_at", "completed_at", "updated_at",
            "file_counts", "extraction_counts", "finding_counts", "severity_counts", "risk", "progress", "actions",
        ]
        read_only_fields = fields

    def get_risk(self, scan):
        """FR-075 to FR-077, FR-080: the score with every factor that produced it, and its limits."""
        result = compute_scan_risk(scan.pk)
        if result is None:
            return None
        return {"score": result.value, "band": result.band, "band_label": result.band_label,
                "factors": list(result.factors), "limitation": result.limitation,
                "policy_version": RISK_POLICY_VERSION,
                # FR-077's interpretation, sent with the score so the page never repeats the thresholds.
                "bands": [{"from": lowest, "band": key, "label": label} for lowest, key, label in BANDS]}

    def get_severity_counts(self, scan):
        """Findings per level, most serious first. "not_assessed": found before severity existed."""
        counts = {level: 0 for level in LEVELS} | {"not_assessed": 0}
        for row in scan.findings.order_by().values("severity").annotate(n=Count("id")):
            counts[row["severity"] or "not_assessed"] = row["n"]
        return counts

    def get_file_counts(self, scan):
        counts = {status: 0 for status in ScannedFile.Status.values}
        for row in scan.files.order_by().values("processing_status").annotate(n=Count("id")):
            counts[row["processing_status"]] = row["n"]
        return counts

    def get_extraction_counts(self, scan):
        """How completely each processed file was read (FR-028)."""
        counts = {status: 0 for status in ScannedFile.Extraction.values if status != "not_started"}
        processed = scan.files.filter(processing_status__in=PROCESSED)
        for row in processed.order_by().values("extraction_status").annotate(n=Count("id")):
            counts[row["extraction_status"]] = row["n"]
        return counts

    def get_finding_counts(self, scan):
        """Findings per type, most common first - counts only."""
        rows = scan.findings.order_by().values("subcategory").annotate(n=Count("id")).order_by("-n", "subcategory")
        return [
            {"type": row["subcategory"], "label": TYPE_LABELS.get(row["subcategory"], row["subcategory"]),
             "count": row["n"]}
            for row in rows
        ]

    def get_progress(self, scan):
        """NFR-002: accepted files the worker has finished, out of all accepted files."""
        accepted = scan.files.filter(processing_status__in=ACCEPTED).count()
        return {"done": scan.processed_files, "total": accepted}

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
    """One inventory row. The storage location and hash stay server-side, and
    no extracted text exists to send: stats are counts, notes fixed wording."""

    status = serializers.CharField(source="processing_status", read_only=True)
    status_display = serializers.CharField(source="get_processing_status_display", read_only=True)
    reason = serializers.CharField(source="error_summary", read_only=True)
    extraction_status_display = serializers.CharField(source="get_extraction_status_display", read_only=True)
    duplicate_of_path = serializers.CharField(
        source="duplicate_of.relative_path", default=None, read_only=True
    )

    class Meta:
        model = ScannedFile
        fields = [
            "id", "file_name", "relative_path", "file_type", "file_size", "status",
            "status_display", "reason", "extraction_status", "extraction_status_display",
            "extraction_detail", "extraction_stats", "extraction_notes", "detection_stats", "processed_at",
            "duplicate_of_path", "created_at",
        ]
        read_only_fields = fields


class FindingSerializer(serializers.ModelSerializer):
    """One finding, in the SRS's own field names (7.2.4). The value and the
    preview are masked, and nothing raw exists to send (D-032)."""

    category_display = serializers.CharField(source="get_category_display", read_only=True)
    subcategory_display = serializers.SerializerMethodField()
    severity_display = serializers.CharField(source="get_severity_display", default=None, read_only=True)
    review_status_display = serializers.CharField(source="get_review_status_display", read_only=True)
    file_id = serializers.UUIDField(source="scanned_file_id", read_only=True)
    file_path = serializers.CharField(source="scanned_file.relative_path", read_only=True)
    scan_name = serializers.CharField(source="scan.name", read_only=True)
    risk_band = serializers.SerializerMethodField()

    class Meta:
        model = Finding
        fields = [
            "id", "category", "category_display", "subcategory", "subcategory_display", "severity",
            "severity_display", "severity_reason", "risk_score", "risk_band", "remediation",
            "confidence", "detection_method", "masked_value", "context_preview", "source_location",
            "other_locations", "occurrences", "description", "review_status", "review_status_display",
            "reviewed_at", "file_id", "file_path", "scan_id", "scan_name", "created_at",
        ]
        read_only_fields = fields

    def get_subcategory_display(self, finding):
        return TYPE_LABELS.get(finding.subcategory, finding.subcategory)

    def get_risk_band(self, finding):
        """The band's thresholds live in the engine only - the browser never repeats them."""
        return None if finding.risk_score is None else band(finding.risk_score)[0]


class FindingDetailSerializer(FindingSerializer):
    """Everything about one finding (FR-084), with its review history from the audit log (UC-03)."""

    file_type = serializers.CharField(source="scanned_file.file_type", read_only=True)
    reviewed_by = serializers.CharField(source="reviewed_by.username", default=None, read_only=True)
    history = serializers.SerializerMethodField()

    class Meta(FindingSerializer.Meta):
        fields = FindingSerializer.Meta.fields + ["file_type", "reviewed_by", "history"]
        read_only_fields = fields

    def get_history(self, finding):
        records = AuditLog.objects.filter(resource_type="finding", resource_id=str(finding.pk),
                                          action=REVIEW_ACTION).select_related("user")[:50]
        return [{"from_status": r.safe_metadata.get("from_status"), "to_status": r.safe_metadata.get("to_status"),
                 "by": r.user.username, "at": r.timestamp} for r in records]


class FindingReviewSerializer(serializers.Serializer):
    """The body of PATCH /api/findings/{id}/. Only the review status can change (FR-086)."""

    review_status = serializers.ChoiceField(choices=Finding.ReviewStatus.choices)

    def validate(self, attrs):
        others = set(self.initial_data) - {"review_status"}
        if others:
            raise serializers.ValidationError(
                f"Only review_status can be changed; {', '.join(sorted(others))} cannot."
            )
        return attrs


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
