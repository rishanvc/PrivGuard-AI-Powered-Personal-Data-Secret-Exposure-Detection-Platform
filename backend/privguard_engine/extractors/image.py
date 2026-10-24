"""Text in PNG and JPEG images, read by OCR (FR-027). Cycle 8.

The image's size is checked from its header before Tesseract decodes it (see
ocr.py). Each line Tesseract reads becomes one segment whose location carries
kind "ocr" and the line's box in pixels - which Cycle 10's image redaction
needs to black it out.
"""

from __future__ import annotations

from .base import Limits, NotSupported, Report, Segment
from .ocr import OcrBudget, check_pixels, image_size, run_tesseract

OCR_OFF = "Text in images needs OCR, which is turned off on this server."
LOW_CONFIDENCE = 70  # average word confidence (0-100) below which a note warns of misreading


def ocr_segments(lines, location: dict, report: Report):
    """Segments from OCR lines, counting words and confidence into the report."""
    for number, line in enumerate(lines, 1):
        report.count("ocr_words", len(line.text.split()))
        report.count("ocr_lines")
        yield Segment(line.text, {**location, "line": number, "kind": "ocr", "ocr_box": ",".join(map(str, line.box))})


def note_confidence(lines, report: Report, where: str) -> None:
    """SRS 9.5: say when OCR confidence is too low to trust."""
    if not lines:
        return
    mean = sum(line.confidence for line in lines) / len(lines)
    if mean < LOW_CONFIDENCE:
        report.note(f"OCR confidence was low in {where} (average {mean:.0f} of 100): characters may be misread, "
                    "and sensitive data missed.")


def extract_image(path: str, report: Report, limits: Limits):
    config = limits.ocr
    if config is None:
        raise NotSupported(OCR_OFF)
    width, height = image_size(path)
    report.set("image_width", width)
    report.set("image_height", height)
    check_pixels(width, height, config)

    lines = run_tesseract(path, config, OcrBudget(config.time_budget).remaining())
    if not lines:
        report.note("OCR found no text in this image.")
    note_confidence(lines, report, "this image")
    yield from ocr_segments(lines, {}, report)
