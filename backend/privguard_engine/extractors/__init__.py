"""Extraction: turn a file into Segments - text plus location (FR-020 to FR-029).

Framework-free (D-002): nothing here imports Django, which is what lets the
worker run extraction in a small, killable child process (Stage 4B).

    result = extract_file(path, "pdf", sink=print)

Extracted text is handed to `sink` and never stored (FR-115). To look at what
an extractor produces for a LOCAL file:

    python -m privguard_engine.extractors ../samples/extraction-demo/deck.pptx
"""

from __future__ import annotations

from .base import (
    EXTRACTION_VERSION,
    ExtractionError,
    ExtractionResult,
    ExtractionStatus,
    Limits,
    NotSupported,
    Report,
    Segment,
    Sink,
    run_extractor,
)
from .delimited import extract_delimited
from .ooxml import extract_docx, extract_pptx
from .pdf import extract_pdf
from .spreadsheet import extract_xlsx
from .text import detect_encoding, extract_text

# file_type (decided at intake, from the file's content) -> extractor
EXTRACTORS = {
    **dict.fromkeys(("text", "code", "config", "env", "key", "json", "yaml", "xml"), extract_text),
    "csv": extract_delimited,
    "xlsx": extract_xlsx,
    "docx": extract_docx,
    "pptx": extract_pptx,
    "pdf": extract_pdf,
}


def extract_file(path: str, file_type: str, *, limits: Limits | None = None, sink: Sink | None = None) -> ExtractionResult:
    """Extract one stored file. Never raises for problems in the FILE - those become a status."""
    extractor = EXTRACTORS.get(file_type)
    if extractor is None:
        return ExtractionResult(ExtractionStatus.NOT_SUPPORTED, "No extractor exists for this file type.")
    return run_extractor(extractor, path, limits or Limits(), sink)


__all__ = [
    "EXTRACTION_VERSION",
    "EXTRACTORS",
    "ExtractionError",
    "ExtractionResult",
    "ExtractionStatus",
    "Limits",
    "NotSupported",
    "Report",
    "Segment",
    "detect_encoding",
    "extract_file",
]
