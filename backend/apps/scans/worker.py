"""The scan worker: claim a queued scan, extract and search its files, finish it (FR-082, FR-089).

The Scan table IS the queue: status "queued" means "waiting for a worker", so
there is one source of truth. Extraction and detection run in an isolated
child process (privguard_engine.isolation), which returns masked findings
only; this module decides what each outcome means for the file and the scan.

    python manage.py run_worker          # keeps running
    python manage.py run_worker --once   # empties the queue, then exits
"""

from __future__ import annotations

import logging
import os
import socket
import time
from collections.abc import Callable
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import DateTimeField, F, Q, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from privguard_engine.detectors import DETECTION_VERSION, DETECTORS, DetectionConfig
from privguard_engine.extractors import EXTRACTION_VERSION, ExtractionStatus, Limits
from privguard_engine.isolation import CANCELLED, DONE, ERROR, TIMEOUT, ExtractionSupervisor, Job, Outcome

from .models import Finding, Scan, ScannedFile, WorkerHeartbeat

logger = logging.getLogger(__name__)

S = Scan.Status
FS = ScannedFile.Status
E = ScannedFile.Extraction
FINISHED_FILES = (FS.COMPLETED, FS.FAILED)

POISON = (
    "Processing stopped unexpectedly while this file was being read, so it was skipped "
    "to avoid repeating the problem. Scan it again to retry."
)
CRASHED = "The extraction process stopped unexpectedly on this file. It may be malformed."
MISSING = "The stored copy of this file could not be found."
INTERNAL = (
    "PrivGuard hit an internal error while searching this file ({kind} at {where}), so it was skipped. "
    "The file itself may be fine - this is a bug worth reporting."
)

RunJob = Callable[[Job, Callable[[], bool]], Outcome]


def extraction_limits() -> Limits:
    return Limits(
        max_chars=settings.EXTRACTION_MAX_CHARS,
        max_pages=settings.EXTRACTION_MAX_PAGES,
        max_cells=settings.EXTRACTION_MAX_CELLS,
    )


def detection_config() -> DetectionConfig:
    return DetectionConfig(region=settings.DETECTION_REGION)


# ---------------------------------------------------------------- the rules

def final_status(extraction_statuses: list[str]) -> str:
    """The honest scan-level outcome, from each processed file's extraction status.

    completed            every file was fully read
    partially_completed  some file was only partly read, or not at all - but something was read
    failed               nothing could be read
    """
    fully = extraction_statuses.count(E.SUCCEEDED)
    partly = extraction_statuses.count(E.PARTIAL)
    if fully + partly == 0:
        return S.FAILED
    if fully == len(extraction_statuses):
        return S.COMPLETED
    return S.PARTIALLY_COMPLETED


# ---------------------------------------------------------------- claiming and recovery

def claim_next_scan() -> Scan | None:
    """Take the oldest queued scan, or return None.

    SELECT ... FOR UPDATE SKIP LOCKED: a row another worker has locked is
    SKIPPED rather than waited for, so two workers never claim the same scan.
    """
    now = timezone.now()
    with transaction.atomic():
        scan = (
            Scan.objects.select_for_update(skip_locked=True)
            .filter(status=S.QUEUED)
            .order_by("created_at")
            .first()
        )
        if scan is None:
            return None
        Scan.objects.filter(pk=scan.pk).update(
            status=S.PROCESSING,
            heartbeat_at=now,
            updated_at=now,
            # Which rules searched this scan (FR-108), so findings can be compared across versions.
            configuration={
                **scan.configuration,
                "extraction_version": EXTRACTION_VERSION,
                "detection_version": DETECTION_VERSION,
                "detectors": sorted(DETECTORS),
                "phone_region": settings.DETECTION_REGION,
            },
            # Keep the original start time when a scan resumes after recovery.
            started_at=Coalesce(F("started_at"), Value(now, output_field=DateTimeField())),
        )
    scan.refresh_from_db()
    return scan


def recover_stale_scans() -> int:
    """Put scans abandoned by a dead worker back in the queue.

    The file that was mid-processing is marked FAILED, not retried: if that
    file is what crashed the worker, retrying it would crash the next worker
    too - forever (a "poison" file). The scan's other files continue.
    """
    now = timezone.now()
    stale = Q(heartbeat_at__lt=now - timedelta(seconds=settings.WORKER_STALE_SECONDS)) | Q(heartbeat_at__isnull=True)
    recovered = 0
    for scan_id in Scan.objects.filter(stale, status=S.PROCESSING).values_list("pk", flat=True):
        with transaction.atomic():
            # Only if STILL stale: a live worker may have written a heartbeat meanwhile.
            if not Scan.objects.filter(stale, pk=scan_id, status=S.PROCESSING).update(
                status=S.QUEUED, heartbeat_at=None, updated_at=now
            ):
                continue
            ScannedFile.objects.filter(scan_id=scan_id, processing_status=FS.PROCESSING).update(
                processing_status=FS.FAILED, extraction_status=E.FAILED, extraction_detail=POISON, processed_at=now
            )
            _refresh_counters(scan_id)
        recovered += 1
        logger.warning("Recovered scan %s from a worker that stopped", scan_id)
    return recovered


# ---------------------------------------------------------------- processing

class _Pulse:
    """While waiting on the child: write heartbeats, and notice cancellation."""

    def __init__(self, scan_id, on_beat: Callable[[], None] | None):
        self.scan_id = scan_id
        self.on_beat = on_beat
        self.last_beat = self.last_check = time.monotonic()

    def beat(self) -> None:
        Scan.objects.filter(pk=self.scan_id, status=S.PROCESSING).update(heartbeat_at=timezone.now())
        if self.on_beat:
            self.on_beat()
        self.last_beat = time.monotonic()

    def keep_waiting(self) -> bool:
        """Called every fraction of a second by the supervisor. False = stop this file."""
        now = time.monotonic()
        if now - self.last_beat >= settings.WORKER_HEARTBEAT_SECONDS:
            self.beat()
        if now - self.last_check >= 1.0:
            self.last_check = now
            return _status(self.scan_id) == S.PROCESSING  # cancelled (or deleted) -> stop
        return True


def process_scan(scan: Scan, run_job: RunJob, *, on_beat: Callable[[], None] | None = None) -> str:
    """Extract every pending file of a CLAIMED scan.

    Returns the scan's final status - or "cancelled" if the user cancelled it.
    `run_job` is ExtractionSupervisor.run in production and a stand-in in tests.
    """
    limits, detection = extraction_limits(), detection_config()
    pulse = _Pulse(scan.pk, on_beat)
    while True:
        if _status(scan.pk) != S.PROCESSING:
            return "cancelled"
        record = scan.files.filter(processing_status=FS.PENDING).order_by("relative_path", "created_at").first()
        if record is None:
            return _finish(scan)
        # pending -> processing, only if nobody else changed it meanwhile
        if not ScannedFile.objects.filter(pk=record.pk, processing_status=FS.PENDING).update(
            processing_status=FS.PROCESSING
        ):
            continue

        path = record.stored_file.path
        if not os.path.exists(path):
            _record_failure(record, MISSING, seconds=0.0)
        else:
            outcome = run_job(Job(path, record.file_type, limits, detection), pulse.keep_waiting)
            if outcome.kind == CANCELLED:
                _release(record)  # it was not processed: back to pending
                continue          # the loop's first check returns "cancelled"
            _record_outcome(record, outcome)
        _refresh_counters(scan.pk)
        pulse.beat()


def _record_outcome(record: ScannedFile, outcome: Outcome) -> None:
    if outcome.kind == ERROR:
        error = outcome.result
        logger.error("Internal error on file %s: %s at %s", record.pk, error.kind, error.where)
        _record_failure(record, INTERNAL.format(kind=error.kind, where=error.where), seconds=outcome.seconds)
        return
    if outcome.kind != DONE:
        message = (
            f"Reading this file took longer than {settings.EXTRACTION_TIMEOUT_SECONDS} seconds, so it was stopped."
            if outcome.kind == TIMEOUT else CRASHED
        )
        _record_failure(record, message, seconds=outcome.seconds)
        return
    extraction = outcome.result.extraction
    # Searched only if some text was actually read: a file nobody could read
    # must not count as "searched, found nothing".
    searched = outcome.result.detection is not None and extraction.status in (
        ExtractionStatus.SUCCEEDED, ExtractionStatus.PARTIAL
    )
    with transaction.atomic():  # the file's result and its findings: all or nothing (SRS 7.4)
        # Compare-and-swap, as for the scan's final status: if recovery already
        # gave up on this file (a worker that went silent for minutes, say),
        # its late result is dropped rather than stored twice.
        if not ScannedFile.objects.filter(pk=record.pk, processing_status=FS.PROCESSING).update(
            extraction_status=extraction.status.value,
            extraction_detail=extraction.reason[:500],
            extraction_stats={**extraction.stats, "seconds": round(outcome.seconds, 2)},  # counts only - no text
            extraction_notes=list(extraction.notes),
            detection_stats=outcome.result.detection if searched else None,
            processing_status=FS.FAILED if extraction.status is ExtractionStatus.FAILED else FS.COMPLETED,
            processed_at=timezone.now(),
        ):
            return
        if searched:
            Finding.objects.bulk_create(_finding_rows(record, outcome.result.findings), batch_size=500)


def _finding_rows(record: ScannedFile, findings) -> list[Finding]:
    return [
        Finding(
            scan_id=record.scan_id, scanned_file=record, category=f.category, subcategory=f.type,
            confidence=f.confidence, detection_method=f.method, detection_version=DETECTION_VERSION,
            masked_value=f.masked_value, context_preview=f.context, source_location=dict(f.location),
            other_locations=[dict(location) for location in f.more_locations], occurrences=f.occurrences,
            description=f.explanation,
        )
        for f in findings
    ]


def _record_failure(record: ScannedFile, message: str, *, seconds: float) -> None:
    ScannedFile.objects.filter(pk=record.pk).update(
        processing_status=FS.FAILED, extraction_status=E.FAILED, extraction_detail=message,
        extraction_stats={"seconds": round(seconds, 2)}, processed_at=timezone.now(),
    )


def _release(record: ScannedFile) -> None:
    ScannedFile.objects.filter(pk=record.pk, processing_status=FS.PROCESSING).update(processing_status=FS.PENDING)


def _requeue(scan_id) -> None:
    """Graceful stop: the scan continues with its pending files next time."""
    ScannedFile.objects.filter(scan_id=scan_id, processing_status=FS.PROCESSING).update(processing_status=FS.PENDING)
    Scan.objects.filter(pk=scan_id, status=S.PROCESSING).update(status=S.QUEUED, heartbeat_at=None, updated_at=timezone.now())


def _status(scan_id) -> str | None:
    return Scan.objects.filter(pk=scan_id).values_list("status", flat=True).first()


def _refresh_counters(scan_id) -> None:
    files = ScannedFile.objects.filter(scan_id=scan_id)
    searched = files.filter(detection_stats__isnull=False).exists()
    Scan.objects.filter(pk=scan_id).update(
        processed_files=files.filter(processing_status__in=FINISHED_FILES).count(),
        failed_files=files.filter(processing_status=FS.FAILED).count(),
        # Grows file by file while the scan runs; NULL until a file has really been searched (D-027).
        total_findings=Finding.objects.filter(scan_id=scan_id).count() if searched else None,
    )


def _finish(scan: Scan) -> str:
    statuses = list(
        scan.files.filter(processing_status__in=FINISHED_FILES).values_list("extraction_status", flat=True)
    )
    status = final_status(statuses)
    incomplete = len(statuses) - statuses.count(E.SUCCEEDED)
    summary = "" if status == S.COMPLETED else (
        f"{incomplete} of {len(statuses)} files could not be fully read. Each file shows the reason."
    )
    now = timezone.now()
    # Compare-and-swap: if the user cancelled at the last moment, cancelled stands.
    if Scan.objects.filter(pk=scan.pk, status=S.PROCESSING).update(
        status=status, completed_at=now, heartbeat_at=None, updated_at=now, error_summary=summary
    ):
        return status
    return "cancelled"


# ---------------------------------------------------------------- the loop

def run_worker(*, once: bool = False, log: Callable[[str], None] = logger.info, run_job: RunJob | None = None) -> int:
    """Process queued scans until stopped with Ctrl+C - or, with once=True, until the queue is empty.

    Returns how many scans were processed.
    """
    name = f"{socket.gethostname()}:{os.getpid()}"
    started = timezone.now()
    last_seen = {"at": 0.0}

    def heartbeat(force: bool = False) -> None:
        if force or time.monotonic() - last_seen["at"] >= settings.WORKER_HEARTBEAT_SECONDS:
            WorkerHeartbeat.objects.update_or_create(name=name, defaults={"started_at": started, "last_seen": timezone.now()})
            last_seen["at"] = time.monotonic()

    heartbeat(force=True)
    WorkerHeartbeat.objects.filter(last_seen__lt=started - timedelta(days=1)).delete()  # long-dead workers

    supervisor = ExtractionSupervisor(timeout=settings.EXTRACTION_TIMEOUT_SECONDS)
    run_job = run_job or supervisor.run
    current: Scan | None = None
    processed = 0
    try:
        if recovered := recover_stale_scans():
            log(f"Recovered {recovered} scan(s) left behind by a worker that stopped.")
        last_recovery = time.monotonic()
        log(f"Worker {name} is waiting for queued scans. Press Ctrl+C to stop.")
        while True:
            heartbeat()
            current = claim_next_scan()
            if current is None:
                if once:
                    break
                if time.monotonic() - last_recovery > settings.WORKER_STALE_SECONDS / 2:
                    recover_stale_scans()
                    last_recovery = time.monotonic()
                time.sleep(settings.WORKER_POLL_SECONDS)
                continue
            pending = current.files.filter(processing_status=FS.PENDING).count()
            log(f"Scan {current.pk}: extracting {pending} file(s)...")
            result = process_scan(current, run_job, on_beat=heartbeat)
            found = Scan.objects.filter(pk=current.pk).values_list("total_findings", flat=True).first()
            log(f"Scan {current.pk}: {result}" + (f", {found} finding(s)." if found is not None else "."))
            current = None
            processed += 1
    except KeyboardInterrupt:
        if current is not None:
            _requeue(current.pk)
            log(f"Stopped. Scan {current.pk} went back to the queue and will continue next time.")
        else:
            log("Stopped.")
    finally:
        supervisor.close()
        WorkerHeartbeat.objects.filter(name=name).delete()
    return processed
