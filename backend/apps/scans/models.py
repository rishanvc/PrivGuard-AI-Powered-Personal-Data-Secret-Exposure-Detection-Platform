"""Scan and file-inventory models (SRS 7.2.2, 7.2.3).

Rows here describe users' sensitive files, so two rules apply throughout:
  * nothing stores file CONTENT - only metadata, a hash, and the private
    storage location of accepted files (FR-115);
  * every reason/summary text is fixed, human-written wording, never text
    taken from inside a file.
"""

import uuid

from django.conf import settings
from django.db import models

from .storage import private_upload_storage, upload_path


class Scan(models.Model):
    class ScanType(models.TextChoices):
        FILES = "files", "Files"
        FOLDER = "folder", "Folder"
        REPOSITORY = "repository", "Repository"  # Cycle 8

    class Status(models.TextChoices):  # FR-082
        DRAFT = "draft", "Draft"
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        PARTIALLY_COMPLETED = "partially_completed", "Partially completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    # UUIDs, not sequential integers: /api/scans/42/ would reveal roughly how
    # many scans exist and invite guessing 43. Ownership checks already make
    # guessing useless (404); UUIDs remove the leak as well.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # PROTECT, not CASCADE: deleting a user must not silently delete their scan
    # ROWS while leaving their sensitive FILES on disk (Django never deletes
    # files when it deletes rows). Scans are removed through
    # services.delete_scan, which deletes the files first.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="scans")

    name = models.CharField(max_length=120)
    scan_type = models.CharField(max_length=20, choices=ScanType.choices)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)

    total_files = models.PositiveIntegerField(default=0)
    processed_files = models.PositiveIntegerField(default=0)  # accepted files the worker has finished
    failed_files = models.PositiveIntegerField(default=0)     # ...of which could not be read
    # NULL means "nobody searched" - which is never the same as 0 findings.
    # Stays NULL until at least one of the scan's files has been searched.
    total_findings = models.PositiveIntegerField(null=True, blank=True, default=None)
    risk_score = models.PositiveSmallIntegerField(null=True, blank=True)  # 0-100, Cycle 7

    # Safe scan options and the limits in force - never credentials (SRS 7.2.2).
    configuration = models.JSONField(default=dict, blank=True)
    error_summary = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)    # processing began (Cycle 4)
    completed_at = models.DateTimeField(null=True, blank=True)  # reached a finished state
    updated_at = models.DateTimeField(auto_now=True)
    # Written every few seconds by the worker while processing. A stale value
    # means the worker died mid-scan, and recovery takes over (apps.scans.worker).
    heartbeat_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "privguard_scan"
        ordering = ["-created_at"]
        indexes = [  # SRS 7.4: index frequently queried fields
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_status_display()})"


class ScannedFile(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"           # accepted, waiting to be processed
        PROCESSING = "processing", "Processing"  # Cycle 4
        COMPLETED = "completed", "Completed"     # Cycle 4
        FAILED = "failed", "Failed"              # Cycle 4
        SKIPPED = "skipped", "Skipped"           # empty, or a duplicate: nothing to process
        REJECTED = "rejected", "Rejected"        # failed validation
        UNSUPPORTED = "unsupported", "Unsupported"  # FR-013

    class Extraction(models.TextChoices):  # FR-028, filled in from Cycle 4
        NOT_STARTED = "not_started", "Not started"
        SUCCEEDED = "succeeded", "Succeeded"
        PARTIAL = "partial", "Partially succeeded"
        FAILED = "failed", "Failed"
        NOT_SUPPORTED = "not_supported", "Not supported"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scan = models.ForeignKey(Scan, on_delete=models.CASCADE, related_name="files")

    file_name = models.CharField(max_length=255)        # sanitised display name
    relative_path = models.CharField(max_length=1024)   # location within the upload
    file_type = models.CharField(max_length=20, blank=True)  # "pdf", "docx", "code"...; "" if unknown
    file_size = models.PositiveBigIntegerField()
    file_hash = models.CharField(max_length=64, blank=True)  # SHA-256; blank if never fully read

    # Empty unless the file was accepted. Stored as <user>/<scan>/<random hex>.
    stored_file = models.FileField(
        upload_to=upload_path, storage=private_upload_storage, max_length=255, blank=True
    )

    processing_status = models.CharField(max_length=16, choices=Status.choices)
    extraction_status = models.CharField(
        max_length=16, choices=Extraction.choices, default=Extraction.NOT_STARTED
    )
    error_summary = models.CharField(max_length=300, blank=True)  # the reason shown to the user

    # Extraction outcome (FR-028). Counts and fixed-wording notes only - the
    # extracted TEXT is never stored (FR-115, D-021).
    extraction_detail = models.CharField(max_length=500, blank=True)  # why it is not "succeeded"
    extraction_stats = models.JSONField(default=dict, blank=True)     # pages, cells, encoding, seconds...
    extraction_notes = models.JSONField(default=list, blank=True)     # e.g. "Hidden sheets were read too..."
    # Detection outcome (Cycle 5): counts per type, and whether findings were
    # capped. NULL = never searched - its text could not be read, or it was
    # processed before detection existed. Never the same as 0 findings.
    detection_stats = models.JSONField(null=True, blank=True, default=None)
    processed_at = models.DateTimeField(null=True, blank=True)

    # FR-017: identical content within a scan is stored and processed once,
    # but every location is still recorded (FR-078).
    duplicate_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="duplicates"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "privguard_scanned_file"
        ordering = ["relative_path", "created_at"]
        indexes = [
            models.Index(fields=["scan", "processing_status"]),
            models.Index(fields=["scan", "file_hash"]),
        ]

    def __str__(self) -> str:
        return f"{self.relative_path} ({self.get_processing_status_display()})"


class Finding(models.Model):
    """One sensitive value found in one file (SRS 7.2.4).

    Holds a MASKED value and a MASKED preview only: raw values never leave the
    isolated extraction child (D-032). Repeats of one value in one file are a
    single finding, with each location listed.
    """

    class Category(models.TextChoices):
        PERSONAL = "personal", "Personal information"
        SECRET = "secret", "Secret or credential"        # Cycle 6
        FINANCIAL = "financial", "Financial information"  # Cycle 6

    class Severity(models.TextChoices):  # FR-073; assigned from Cycle 6
        CRITICAL = "critical", "Critical"
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"
        INFORMATIONAL = "informational", "Informational"

    class ReviewStatus(models.TextChoices):  # FR-086; users change it from Cycle 7
        NEW = "new", "New"
        CONFIRMED = "confirmed", "Confirmed"
        FALSE_POSITIVE = "false_positive", "False positive"
        RESOLVED = "resolved", "Resolved"
        ACCEPTED_RISK = "accepted_risk", "Accepted risk"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scan = models.ForeignKey(Scan, on_delete=models.CASCADE, related_name="findings")
    scanned_file = models.ForeignKey(ScannedFile, on_delete=models.CASCADE, related_name="findings")

    category = models.CharField(max_length=20, choices=Category.choices)
    subcategory = models.CharField(max_length=40)  # "email_address"...; labels in detectors.TYPE_LABELS
    # NULL = not assessed: found by a scan that ran before severity existed (Cycle 6).
    severity = models.CharField(max_length=16, choices=Severity.choices, null=True, blank=True)
    severity_reason = models.TextField(blank=True)  # FR-076: why this level, in fixed wording
    confidence = models.FloatField()  # fixed per rule: a ranking aid, not a probability (D-031)
    detection_method = models.CharField(max_length=30)  # "pattern", "pattern + checksum", "context"...
    detection_version = models.PositiveSmallIntegerField()  # which version of the rules found it (SRS 7.3)

    masked_value = models.CharField(max_length=300)
    context_preview = models.TextField(blank=True)               # masked (FR-085)
    source_location = models.JSONField()                         # the most confident occurrence
    other_locations = models.JSONField(default=list, blank=True)  # further distinct locations, capped
    occurrences = models.PositiveIntegerField(default=1)

    risk_score = models.PositiveSmallIntegerField(null=True, blank=True)  # Cycle 7
    description = models.TextField()                # why it was flagged: fixed wording, never the file's text
    remediation = models.TextField(blank=True)      # Cycle 7
    review_status = models.CharField(max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.NEW)
    # The LAST review, for display. The full history is in the audit log (Cycle 7, UC-03).
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                    related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "privguard_finding"
        ordering = ["-confidence", "created_at"]
        indexes = [  # SRS 7.4: scan identifiers, severity, category, review status
            models.Index(fields=["scan", "category"]),
            models.Index(fields=["scan", "severity"]),
            models.Index(fields=["scan", "review_status"]),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(confidence__gte=0, confidence__lte=1),
                                   name="finding_confidence_between_0_and_1"),
            models.CheckConstraint(condition=models.Q(occurrences__gte=1), name="finding_occurs_at_least_once"),
        ]

    def __str__(self) -> str:
        return f"{self.subcategory} {self.masked_value}"


class WorkerHeartbeat(models.Model):
    """One row per running scan worker, refreshed every few seconds.

    Lets /api/health/ say whether queued scans will actually be processed
    (FR-119, FR-120). A worker removes its row when it stops cleanly; rows
    from workers that crashed simply grow old and are ignored.
    """

    name = models.CharField(max_length=200, primary_key=True)  # "<host>:<process id>"
    started_at = models.DateTimeField()
    last_seen = models.DateTimeField()

    class Meta:
        db_table = "privguard_worker_heartbeat"

    def __str__(self) -> str:
        return self.name
