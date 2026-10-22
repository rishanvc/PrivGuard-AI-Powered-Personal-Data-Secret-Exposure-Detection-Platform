"""Request-level guards that must run before the request body is read."""

import logging

from django.conf import settings
from django.core.exceptions import RequestDataTooBig, TooManyFieldsSent, TooManyFilesSent
from django.http import JsonResponse

logger = logging.getLogger(__name__)

MB = 1024 * 1024
# Room for multipart framing (boundaries, part headers) and the small text
# fields that travel with the files: scan name, scan type, one path per file.
MULTIPART_ALLOWANCE = 512 * 1024


class RequestSizeLimitMiddleware:
    """Reject requests whose declared size exceeds the per-scan limit (FR-019).

    Why middleware rather than a check in the view: DRF's CSRF check reads
    request.POST, which parses the ENTIRE multipart body - every uploaded file
    written to disk - before the view runs. A size check inside the view would
    happen after the disk had already been filled.

    Under WSGI, checking Content-Length is sufficient: Django wraps the input
    in a LimitedStream and never reads past the declared length, so a client
    cannot declare 1 KB and then send 1 GB. ASGI deployments need an
    equivalent server-level limit (Cycle 12).

    Also turns Django's own parser limits (too many files or fields, oversized
    form data) into JSON errors instead of an HTML "Bad Request" page, so the
    API's error shape stays consistent (SRS 11).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            declared = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            return JsonResponse({"detail": "Invalid Content-Length header."}, status=400)

        # Read from settings on every request, so a changed limit (or a test
        # override) takes effect without a restart.
        limit = settings.MAX_TOTAL_SCAN_SIZE_MB * MB + MULTIPART_ALLOWANCE
        if declared > limit:
            logger.warning("Rejected oversized request to %s (%d bytes declared)", request.path, declared)
            return JsonResponse(
                {"detail": f"Upload too large. One scan can contain at most {settings.MAX_TOTAL_SCAN_SIZE_MB} MB."},
                status=413,
            )
        return self.get_response(request)

    def process_exception(self, request, exception):
        if isinstance(exception, TooManyFilesSent):
            message = (
                f"Too many files. One scan can contain at most "
                f"{settings.DATA_UPLOAD_MAX_NUMBER_FILES} files."
            )
        elif isinstance(exception, (TooManyFieldsSent, RequestDataTooBig)):
            message = "The request contains too much form data."
        else:
            return None  # not ours - let Django handle it
        logger.warning("Rejected request to %s: %s", request.path, type(exception).__name__)
        return JsonResponse({"detail": message}, status=400)
