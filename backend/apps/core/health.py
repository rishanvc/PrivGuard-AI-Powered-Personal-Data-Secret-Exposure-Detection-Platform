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

from django.conf import settings
from django.db import connection

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


def check_ocr():
    """OCR is optional and arrives in Cycle 8 (FR-027)."""
    if not settings.OCR_ENABLED:
        return "disabled", "OCR disabled (OCR_ENABLED=False)"
    return "error", "OCR enabled but not yet implemented"


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
    "ocr": check_ocr,
    "ai": check_ai,
}

# A failure in these means the application cannot do its job.
REQUIRED_COMPONENTS = {"backend", "database"}


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
