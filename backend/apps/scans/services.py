"""Scan operations. Views stay thin; the rules live here."""

from __future__ import annotations

import hashlib
import logging
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from privguard_engine.intake import (
    INTAKE_VERSION,
    UnsafePath,
    Verdict,
    clean_display_text,
    display_name,
    inspect_file,
    safe_relative_path,
)

from . import lifecycle
from .models import Scan, ScannedFile
from .storage import private_upload_storage, scan_dir_name

logger = logging.getLogger(__name__)

MB = 1024 * 1024
F = ScannedFile.Status
NOT_ACCEPTED = (F.REJECTED, F.UNSUPPORTED, F.SKIPPED)


class ScanStateError(Exception):
    """The operation isn't allowed in the scan's current state. User-facing message."""


class ScanStorageError(Exception):
    """Stored files could not be removed. User-facing message."""


@dataclass(frozen=True)
class IncomingFile:
    uploaded: object                  # a Django UploadedFile: .name, .size, file-like
    relative_path: str | None = None  # folder uploads only, e.g. "src/config/.env"


# ---------------------------------------------------------------- create

def create_scan(*, user, name: str, scan_type: str, files: list[IncomingFile]) -> Scan:
    """Create a draft scan and inventory every file (FR-008, FR-009, FR-015).

    One bad file never sinks the scan (NFR-028): it is recorded as rejected,
    unsupported or skipped, with a reason, and the rest carry on.

    The database can roll back; the filesystem can't. Accepted files are
    written into a fresh per-scan folder, and if anything fails, that whole
    folder is removed before the error propagates - no orphaned sensitive files.
    """
    scan_id = uuid.uuid4()
    scan_dir = Path(private_upload_storage.path(scan_dir_name(user.pk, scan_id)))

    try:
        with transaction.atomic():
            scan = Scan.objects.create(
                id=scan_id,
                user=user,
                name=clean_display_text(name, 120) or _default_name(scan_type, files),
                scan_type=scan_type,
                total_files=len(files),
                configuration={
                    "intake_version": INTAKE_VERSION,
                    "limits": {
                        "max_file_mb": settings.MAX_UPLOAD_SIZE_MB,
                        "max_total_mb": settings.MAX_TOTAL_SCAN_SIZE_MB,
                        "max_files": settings.MAX_FILES_PER_SCAN,
                    },
                },
            )
            accepted_by_hash: dict[str, ScannedFile] = {}
            max_file_bytes = settings.MAX_UPLOAD_SIZE_MB * MB
            for incoming in files:
                _inventory_file(scan, incoming, max_file_bytes, accepted_by_hash)
    except Exception:
        shutil.rmtree(scan_dir, ignore_errors=True)
        raise
    return scan


def _inventory_file(scan, incoming: IncomingFile, max_file_bytes: int, accepted_by_hash: dict) -> ScannedFile:
    uploaded = incoming.uploaded
    name = display_name(uploaded.name)
    record = ScannedFile(scan=scan, file_name=name, relative_path=name, file_size=uploaded.size)

    # 1. Where the file sat in the upload (folder uploads only).
    if incoming.relative_path is not None:
        try:
            record.relative_path = safe_relative_path(incoming.relative_path)
        except UnsafePath as exc:
            return _record(record, F.REJECTED, str(exc))
        record.file_name = record.relative_path.rsplit("/", 1)[-1]

    # 2. Nothing to scan.
    if uploaded.size == 0:
        return _record(record, F.SKIPPED, "Empty file: there is nothing to scan.")

    # 3. Size, real type and structure - decided by the framework-free engine.
    inspection = inspect_file(record.file_name, uploaded, uploaded.size, max_file_bytes)
    record.file_type = inspection.file_type
    if inspection.verdict is Verdict.REJECTED:
        return _record(record, F.REJECTED, inspection.reason)
    if inspection.verdict is Verdict.UNSUPPORTED:
        return _record(record, F.UNSUPPORTED, inspection.reason)

    # 4. Identical content already accepted in this scan? (FR-017)
    record.file_hash = _sha256(uploaded)
    original = accepted_by_hash.get(record.file_hash)
    if original is not None:
        record.duplicate_of = original
        return _record(record, F.SKIPPED, "Identical to another file in this scan.")

    # 5. Store. The name passed here is ignored: storage.upload_path generates
    #    <user>/<scan>/<random hex>, so the uploader's name never touches disk.
    record.stored_file.save("upload", uploaded, save=False)
    _record(record, F.PENDING, "")
    accepted_by_hash[record.file_hash] = record
    return record


def _record(record: ScannedFile, status: str, reason: str) -> ScannedFile:
    record.processing_status = status
    record.error_summary = reason
    record.save()
    return record


def _sha256(uploaded) -> str:
    digest = hashlib.sha256()
    for chunk in uploaded.chunks():  # chunks() rewinds to the start first
        digest.update(chunk)
    return digest.hexdigest()


def _default_name(scan_type: str, files: list[IncomingFile]) -> str:
    if scan_type == Scan.ScanType.FOLDER:
        for incoming in files:
            try:
                return safe_relative_path(incoming.relative_path or "").split("/", 1)[0][:120]
            except UnsafePath:
                continue
    count = len(files)
    return f"Upload of {count} file{'' if count == 1 else 's'}"


# ---------------------------------------------------------------- lifecycle

def transition(scan: Scan, action: str) -> Scan:
    """Apply a lifecycle action, or raise ScanStateError (FR-082, FR-089)."""
    allowed_from, target = lifecycle.ACTIONS[action]

    if action == "start" and not scan.files.filter(processing_status=F.PENDING).exists():
        raise ScanStateError("Nothing to scan: no file in this scan was accepted.")

    now = timezone.now()
    fields = {"status": target, "updated_at": now}  # .update() skips auto_now, so set it here
    if target in lifecycle.FINISHED:
        fields["completed_at"] = now

    # Compare-and-swap. The WHERE clause re-checks the status inside the same
    # statement the database applies atomically, so if two requests race,
    # exactly one updates a row and the other updates none - even though both
    # read "draft" a moment earlier.
    changed = Scan.objects.filter(pk=scan.pk, status__in=allowed_from).update(**fields)
    scan.refresh_from_db()
    if not changed:
        raise ScanStateError(f"Cannot {action} a scan that is {scan.get_status_display().lower()}.")
    return scan


# ---------------------------------------------------------------- delete

def delete_scan(scan: Scan) -> None:
    """Delete a scan and its stored files (NFR-024). Files first, then records.

    If removing files fails, nothing is deleted and the user can retry. The
    reverse order could leave a "deleted" scan whose sensitive files are still
    on disk - the worst outcome for a privacy tool.
    """
    # The row lock closes a race: without it, a worker could claim the scan
    # between the status check and the deletion and find its files gone. The
    # worker claims with SKIP LOCKED, so it simply passes over this row.
    with transaction.atomic():
        scan = Scan.objects.select_for_update().get(pk=scan.pk)
        if scan.status in lifecycle.UNDELETABLE:
            raise ScanStateError("A scan cannot be deleted while it is processing. Cancel it first.")

        scan_dir = Path(private_upload_storage.path(scan_dir_name(scan.user_id, scan.pk)))
        try:
            shutil.rmtree(scan_dir)
        except FileNotFoundError:
            pass  # nothing was stored (every file rejected), or a retry after partial success
        except OSError:
            logger.exception("Could not remove stored files for scan %s", scan.pk)
            raise ScanStorageError(
                "The scan's stored files could not be removed, so the scan was not deleted. "
                "Another program may have one of them open. Try again shortly."
            )
        scan.delete()


# ---------------------------------------------------------------- dashboard

def dashboard_summary(user) -> dict:
    """FR-081 totals - for this user's scans only."""
    scans = Scan.objects.filter(user=user)
    files = ScannedFile.objects.filter(scan__user=user)
    by_status = {
        row["status"]: row["n"]
        for row in scans.order_by().values("status").annotate(n=Count("id"))
    }
    return {
        "total_scans": scans.count(),
        "scans_by_status": by_status,
        "files_inventoried": files.count(),
        "files_accepted": files.exclude(processing_status__in=NOT_ACCEPTED).count(),
        # Finished by the worker - whether or not their text could be read; how
        # completely each was read is shown per scan (extraction_counts).
        "files_processed": files.filter(processing_status__in=(F.COMPLETED, F.FAILED)).count(),
        # SUM skips NULLs, and is NULL when every scan is: "not searched" survives to the dashboard.
        "total_findings": scans.aggregate(n=Sum("total_findings"))["n"],
        "critical_high_findings": None,  # severity arrives in Cycle 6
    }
