"""PDF text, page by page, via PDFium - Chrome's PDF engine (FR-022, FR-023).

A PDF does not store lines or paragraphs. It stores drawing instructions -
"place glyph 37 at x=72, y=720" - and PDFium reconstructs readable text from
the glyph positions. A page that yields no text is usually a scanned image,
which needs OCR (Cycle 8): such pages are reported, never silently skipped.

PDFium is C++ parsing untrusted input. It is heavily fuzzed (it ships in
Chrome), but this is the main reason extraction runs in an isolated child
process with a timeout (Stage 4B).
"""

from __future__ import annotations

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from .base import ExtractionError, Limits, NotSupported, Report, Segment

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
        empty = 0

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
                empty += 1

        if to_read and empty == to_read:
            raise NotSupported(
                "This PDF has no text layer; it looks like a scanned document. "
                "Reading scanned pages needs OCR, planned for Cycle 8."
            )
        if empty:
            report.set("pages_without_text", empty)
            report.partial(
                f"{empty} of {to_read} pages contain no extractable text; "
                "they may be scanned images (OCR is planned for Cycle 8)."
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
