"""Whether this server can read text in images (Cycle 8) - the one place settings meet the OCR engine.

Intake, the worker and the health check all ask here, so they can never
disagree about whether an image will be read.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

from privguard_engine.extractors.ocr import OcrConfig


def ocr_config() -> OcrConfig | None:
    """The settings the extraction child needs, or None when OCR is off or Tesseract is missing."""
    command = settings.TESSERACT_CMD
    if not settings.OCR_ENABLED or not command or not Path(command).is_file():
        return None
    return OcrConfig(
        command=command,
        languages=settings.OCR_LANGUAGES,
        dpi=settings.OCR_DPI,
        max_pixels=settings.OCR_MAX_MEGAPIXELS * 1_000_000,
        max_pages=settings.OCR_MAX_PAGES,
        time_budget=float(settings.OCR_TIME_BUDGET_SECONDS),
        temp_dir=str(settings.TMP_ROOT),  # private: rendered pages show the user's documents (FR-030)
    )
