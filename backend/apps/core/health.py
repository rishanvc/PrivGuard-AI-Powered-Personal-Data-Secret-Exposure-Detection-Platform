"""Component health checks (FR-119, FR-120).

Each check returns (status, detail):

    "ok"        component is present and working
    "disabled"  optional component intentionally switched off
    "error"     component is required (or enabled) but not working

NFR-032 requires optional components to degrade gracefully, so a disabled OCR
or AI service never makes the system unhealthy.

SECURITY (NFR-019): detail strings are fixed, human-written text. Raw exception
messages are never returned - a psycopg connection error, for example, contains
the database username and host. Exceptions go to the log; the caller gets a
generic string.
"""

import logging
import time
from pathlib import Path

from django.conf import settings
from django.db import connection

from privguard_engine.extractors import ocr

from .version import __version__

logger = logging.getLogger(__name__)


def check_backend():
    return "ok", f"PrivGuard {__version__}"


def check_database():
    """Confirm the database answers a trivial query."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        # Log the real cause locally; never return it.
        logger.exception("Database health check failed")
        return "error", "Database unreachable"
    return "ok", "Connected"


def check_worker():
    """Is a scan worker running? Without one, queued scans wait forever (Cycle 4)."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.scans.models import WorkerHeartbeat

    try:
        last_seen = WorkerHeartbeat.objects.order_by("-last_seen").values_list("last_seen", flat=True).first()
    except Exception:
        logger.exception("Worker health check failed")
        return "error", "Worker status unavailable"
    if last_seen is not None and timezone.now() - last_seen <= timedelta(seconds=settings.WORKER_ALIVE_SECONDS):
        return "ok", f"Running (last seen {int((timezone.now() - last_seen).total_seconds())} s ago)"
    return "error", "Not running: queued scans will wait. Start it with 'python manage.py run_worker'."


_OCR_CACHE_SECONDS = 60
_ocr_cache: dict = {}


def check_ocr():
    """OCR is optional (FR-027, NFR-032): say exactly why it is not available.

    Starting Tesseract twice takes a moment, and the dashboard polls this, so the
    answer is reused for a minute.
    """
    if not settings.OCR_ENABLED:
        return "disabled", "OCR disabled (OCR_ENABLED=False)"
    command = settings.TESSERACT_CMD
    if not command or not Path(command).is_file():
        return "error", "OCR is enabled, but TESSERACT_CMD does not point to tesseract.exe"
    key = (command, settings.OCR_LANGUAGES)
    cached = _ocr_cache.get(key)
    if cached and time.monotonic() - cached[0] < _OCR_CACHE_SECONDS:
        return cached[1]
    found = ocr.version(command)
    if found is None:
        result = ("error", "OCR is enabled, but Tesseract could not be started")
    else:
        missing = set(settings.OCR_LANGUAGES.split("+")) - ocr.languages(command)
        result = (
            ("error", f"Tesseract {found} is missing language data: {', '.join(sorted(missing))}") if missing
            else ("ok", f"Tesseract {found} ({settings.OCR_LANGUAGES})")
        )
    _ocr_cache[key] = (time.monotonic(), result)
    return result


def check_ai():
    """Local LLM is optional and arrives in Cycle 9 (FR-062, FR-063)."""
    if not settings.AI_ENABLED:
        return "disabled", "AI assistance disabled (AI_ENABLED=False)"
    return "error", "AI enabled but not yet implemented"


# Ordered registry. Later cycles replace the placeholder callables above
# without changing the endpoint or the frontend contract.
COMPONENT_CHECKS = {
    "backend": check_backend,
    "database": check_database,
    "worker": check_worker,
    "ocr": check_ocr,
    "ai": check_ai,
}

# A failure in these means the application cannot do its job. Without a
# worker, scans can be created but never processed - genuinely degraded.
REQUIRED_COMPONENTS = {"backend", "database", "worker"}


def collect_health():
    """Run every check and derive an overall status."""
    components = {}
    degraded = False

    for name, check in COMPONENT_CHECKS.items():
        try:
            status, detail = check()
        except Exception:
            logger.exception("Health check %r raised", name)
            status, detail = "error", "Check failed"

        components[name] = {"status": status, "detail": detail}

        if status == "error" and name in REQUIRED_COMPONENTS:
            degraded = True

    return {
        "status": "degraded" if degraded else "ok",
        "version": __version__,
        "components": components,
    }
