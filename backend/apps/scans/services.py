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

from apps.audit import services as audit
from apps.core.ocr import ocr_config
from privguard_engine.detectors import TYPE_LABELS
from privguard_engine.risk import LEVELS, NOT_COUNTED, Counted, ScanScore, band, scan_risk
from privguard_engine.risk.scoring import SERIOUS

from . import lifecycle
from .models import Finding, Scan, ScannedFile
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
    inspection = inspect_file(record.file_name, uploaded, uploaded.size, max_file_bytes, ocr=ocr_config() is not None)
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


# ---------------------------------------------------------------- risk (Cycle 7)

def compute_scan_risk(scan_id) -> ScanScore | None:
    """The scan's 0-100 score and its explanation; None while nothing has been searched (D-027).

    Only the riskiest counted finding and the serious ones change the score, so
    only those rows are loaded - a scan can hold many thousands of findings.
    """
    if Scan.objects.filter(pk=scan_id).values_list("total_findings", flat=True).first() is None:
        return None
    findings = Finding.objects.filter(scan_id=scan_id)
    counted = findings.filter(risk_score__isnull=False).exclude(review_status__in=NOT_COUNTED)
    fields = ("risk_score", "subcategory", "scanned_file__relative_path")
    rows = (list(counted.filter(risk_score__gte=SERIOUS).values_list(*fields))
            or list(counted.order_by("-risk_score").values_list(*fields)[:1]))
    return scan_risk(
        (Counted(risk, f"{TYPE_LABELS.get(kind, kind)} in {path}") for risk, kind, path in rows),
        excluded=findings.filter(review_status__in=NOT_COUNTED).count(),
        not_assessed=findings.filter(risk_score__isnull=True).exclude(review_status__in=NOT_COUNTED).count(),
    )


def refresh_scan_risk(scan_id) -> None:
    """Store the current score - after each file the worker finishes, and after each review (FR-075)."""
    result = compute_scan_risk(scan_id)
    Scan.objects.filter(pk=scan_id).update(risk_score=None if result is None else result.value)


# ---------------------------------------------------------------- review (Cycle 7)

REVIEW_ACTION = "finding.review"


def review_finding(*, finding: Finding, user, status: str) -> Finding:
    """FR-086, UC-03: change a finding's review status, record who did it, and rescore its scan.

    All in one transaction: the status, the audit record and the score change
    together or not at all. The row lock stops two reviews from interleaving.
    A review that changes nothing records nothing.
    """
    with transaction.atomic():
        current = Finding.objects.select_for_update().get(pk=finding.pk)
        previous = current.review_status
        if previous != status:
            Finding.objects.filter(pk=current.pk).update(review_status=status, reviewed_by=user,
                                                         reviewed_at=timezone.now())
            audit.record(user=user, action=REVIEW_ACTION, resource_type="finding", resource_id=current.pk,
                         metadata={"scan_id": str(current.scan_id), "finding_type": current.subcategory,
                                   "from_status": previous, "to_status": status})
            refresh_scan_risk(current.scan_id)
    return Finding.objects.select_related("scanned_file", "scan", "reviewed_by").get(pk=finding.pk)


# ---------------------------------------------------------------- dashboard

def dashboard_summary(user) -> dict:
    """FR-081 totals - for this user's scans only."""
    scans = Scan.objects.filter(user=user)
    files = ScannedFile.objects.filter(scan__user=user)
    by_status = {
        row["status"]: row["n"]
        for row in scans.order_by().values("status").annotate(n=Count("id"))
    }
    # SUM skips NULLs, and is NULL when every scan is: "not searched" survives to the dashboard.
    total_findings = scans.aggregate(n=Sum("total_findings"))["n"]
    searched = total_findings is not None
    findings = Finding.objects.filter(scan__user=user)
    # "Open": not reviewed away as false positive or resolved - the findings that still need attention.
    open_findings = findings.exclude(review_status__in=NOT_COUNTED)

    def counts(queryset, field, keys):
        result = dict.fromkeys(keys, 0)
        for row in queryset.order_by().values(field).annotate(n=Count("id")):
            result[row[field] or "not_assessed"] = row["n"]
        return result

    riskiest = scans.filter(risk_score__isnull=False).order_by("-risk_score", "-created_at")[:5]
    return {
        "total_scans": scans.count(),
        "scans_by_status": by_status,
        "files_inventoried": files.count(),
        "files_accepted": files.exclude(processing_status__in=NOT_ACCEPTED).count(),
        # Finished by the worker - whether or not their text could be read; how
        # completely each was read is shown per scan (extraction_counts).
        "files_processed": files.filter(processing_status__in=(F.COMPLETED, F.FAILED)).count(),
        "total_findings": total_findings,
        # Everything below is NULL while nothing has been searched, like total_findings:
        # "0 critical" must mean "looked, and found none".
        "critical_high_findings": open_findings.filter(
            severity__in=(Finding.Severity.CRITICAL, Finding.Severity.HIGH)
        ).count() if searched else None,
        "severity_counts": counts(open_findings, "severity", (*LEVELS, "not_assessed")) if searched else None,
        "category_counts": counts(open_findings, "category", Finding.Category.values) if searched else None,
        "review_counts": counts(findings, "review_status", Finding.ReviewStatus.values) if searched else None,
        "riskiest_scans": [
            {"id": scan.pk, "name": scan.name, "risk_score": scan.risk_score, "risk_band": band(scan.risk_score)[0],
             "total_findings": scan.total_findings}
            for scan in riskiest
        ],
    }
