"""PDF text, page by page, via PDFium - Chrome's PDF engine (FR-022, FR-023).

A PDF does not store lines or paragraphs. It stores drawing instructions -
"place glyph 37 at x=72, y=720" - and PDFium reconstructs readable text from
the glyph positions. A page that yields no text is usually a scanned image.
With OCR on (Cycle 8) such pages are rendered to images and read by
Tesseract; with it off they are reported, never silently skipped.

PDFium is C++ parsing untrusted input. It is heavily fuzzed (it ships in
Chrome), but this is the main reason extraction runs in an isolated child
process with a timeout (Stage 4B).
"""

from __future__ import annotations

import math
import os

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from .ocr import OcrBudget, run_tesseract, temp_image_path, write_pgm
from .base import ExtractionError, Limits, NotSupported, Report, Segment
from .image import note_confidence, ocr_segments

# Decided from PDFium's numeric error code, not by parsing its message text.
_LOCKED = {pdfium_c.FPDF_ERR_PASSWORD, pdfium_c.FPDF_ERR_SECURITY}
_METADATA_FIELDS = ("Author", "Title", "Subject", "Keywords")


def extract_pdf(path: str, report: Report, limits: Limits):
    try:
        document = pdfium.PdfDocument(path)
    except pdfium.PdfiumError as exc:
        if getattr(exc, "err_code", None) in _LOCKED:
            raise NotSupported(
                "The PDF is password-protected or uses unsupported encryption, so its text cannot be read."
            ) from None
        raise ExtractionError("The PDF is damaged or is not a valid PDF.") from None

    try:
        total = len(document)
        report.set("pages", total)
        to_read = min(total, limits.max_pages)
        empty: list[int] = []

        for index in range(to_read):
            page = document[index]
            try:
                textpage = page.get_textpage()
                try:
                    text = textpage.get_text_range()
                finally:
                    textpage.close()
            finally:
                page.close()

            text = text.replace("\r\n", "\n").replace("\r", "\n")
            if text.strip():
                yield Segment(text, {"page": index + 1})
            else:
                empty.append(index)

        if empty:
            report.set("pages_without_text", len(empty))
            if limits.ocr is not None:
                yield from _ocr_pages(document, empty, limits.ocr, report, only_pages=len(empty) == to_read)
            elif len(empty) == to_read:
                raise NotSupported(
                    "This PDF has no text layer; it looks like a scanned document. "
                    "Reading scanned pages needs OCR, which is turned off on this server."
                )
            else:
                report.partial(
                    f"{len(empty)} of {to_read} pages contain no extractable text; "
                    "they may be scanned images (OCR is turned off on this server)."
                )
        if total > to_read:
            report.partial(f"Only the first {to_read:,} of {total:,} pages were read (the per-file page limit).")

        # Personal data hides in metadata too: an author's full name, for example.
        metadata = document.get_metadata_dict(skip_empty=True)
        for key in _METADATA_FIELDS:
            value = str(metadata.get(key, "")).strip()
            if value:
                yield Segment(value, {"part": "properties", "field": key.lower()})
    finally:
        document.close()


def _ocr_pages(document, indexes: list[int], config, report: Report, *, only_pages: bool):
    """Render each page that had no text, and read it with Tesseract (FR-023).

    Bounded three ways: at most config.max_pages pages, at most config.max_pixels
    per rendered page (the resolution drops for huge pages), and config.time_budget
    seconds in all. Hitting a bound is reported - the file is then partly read.
    """
    budget = OcrBudget(config.time_budget)
    chosen = indexes[:config.max_pages]
    all_lines = []
    for done, index in enumerate(chosen):
        page = document[index]
        try:
            width_pt, height_pt = page.get_size()
            scale = min(config.dpi / 72, math.sqrt(config.max_pixels / max(width_pt * height_pt, 1.0)))
            bitmap = page.render(scale=scale, grayscale=True)
            image = temp_image_path(config)
            try:
                write_pgm(image, bitmap.width, bitmap.height, bitmap.stride, bytes(bitmap.buffer))
                lines = run_tesseract(image, config, budget.remaining(), dpi=round(scale * 72))
            finally:
                bitmap.close()
                if os.path.exists(image):
                    os.remove(image)  # the rendered page shows the document: never left behind
        except ExtractionError as exc:
            if only_pages and done == 0:
                raise  # nothing at all could be read: the file failed, it was not "partly read"
            report.partial(f"OCR read {done} of {len(indexes)} scanned pages, then stopped: {exc}")
            return
        finally:
            page.close()
        all_lines += lines
        report.count("ocr_pages")
        yield from ocr_segments(lines, {"page": index + 1}, report)

    if len(indexes) > len(chosen):
        report.partial(f"OCR read only the first {len(chosen)} of {len(indexes)} scanned pages "
                       "(the per-file OCR page limit).")
    if not all_lines:
        report.note("OCR found no text on the scanned pages.")
    note_confidence(all_lines, report, "the scanned pages")
