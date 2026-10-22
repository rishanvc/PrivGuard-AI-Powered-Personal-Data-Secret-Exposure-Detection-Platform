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
    processed_files = models.PositiveIntegerField(default=0)  # Cycle 4
    failed_files = models.PositiveIntegerField(default=0)     # Cycle 4
    total_findings = models.PositiveIntegerField(default=0)   # Cycle 5
    risk_score = models.PositiveSmallIntegerField(null=True, blank=True)  # 0-100, Cycle 7

    # Safe scan options and the limits in force - never credentials (SRS 7.2.2).
    configuration = models.JSONField(default=dict, blank=True)
    error_summary = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)    # processing began (Cycle 4)
    completed_at = models.DateTimeField(null=True, blank=True)  # reached a finished state
    updated_at = models.DateTimeField(auto_now=True)

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
