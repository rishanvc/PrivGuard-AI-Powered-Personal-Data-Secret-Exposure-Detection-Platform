"""Common shapes for every extractor (FR-028, FR-029).

Every format becomes a stream of Segments - a piece of text plus where it came
from - so detection (Cycle 5) never needs to know whether the source was a PDF,
a spreadsheet or a log file (SRS 6.2, principle 2).

Pure Python, no Django (D-002).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

MB = 1024 * 1024

# Bump when extraction behaviour changes, so each scan records which rules read it.
EXTRACTION_VERSION = 1


class ExtractionStatus(str, Enum):  # FR-028
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    NOT_SUPPORTED = "not_supported"


@dataclass(frozen=True, slots=True)
class Segment:
    """A piece of extracted text and where it came from (FR-029).

    Location keys (all optional):
        line            1-based line number                        text formats, CSV
        page            1-based page                               PDF
        sheet, cell     sheet name, cell reference such as "C7"   XLSX
        row, column     1-based                                    CSV
        header          the column's header text                  CSV, XLSX
        hidden          True for cells on a hidden sheet           XLSX
        slide           1-based, in presentation order             PPTX
        part            "body", "header 1", "comments", "notes", "properties"...
        paragraph       1-based paragraph within the part          DOCX
        kind            "deleted" or "field code": text Word does not display
        field           metadata field name, e.g. "creator"
    """

    text: str
    location: Mapping[str, object]


@dataclass(frozen=True)
class Limits:
    """Per-file resource limits (NFR-003). Hitting one gives PARTIAL, never a silent stop."""

    max_chars: int = 20_000_000
    max_pages: int = 2_000
    max_cells: int = 2_000_000
    max_part_bytes: int = 256 * MB          # one XML part inside an Office file
    max_total_uncompressed: int = 512 * MB  # every part of an Office file together
    max_ratio: int = 250                    # compression ratio allowed for large parts...
    ratio_floor: int = 10 * MB              # ...where "large" starts


class ExtractionError(Exception):
    """The file could not be (fully) read. The message is fixed, user-facing text."""


class NotSupported(ExtractionError):
    """The file is valid but its text can't be extracted, e.g. a password-protected PDF."""


class Report:
    """What an extractor tells the driver besides the segments themselves."""

    def __init__(self):
        self.stats: dict[str, object] = {}
        self.notes: list[str] = []
        self.incomplete: list[str] = []

    def count(self, key: str, amount: int = 1) -> None:
        self.stats[key] = self.stats.get(key, 0) + amount

    def set(self, key: str, value: object) -> None:
        self.stats[key] = value

    def note(self, message: str) -> None:
        """Something worth knowing that does not reduce coverage."""
        if message not in self.notes:
            self.notes.append(message)

    def partial(self, message: str) -> None:
        """Some content could not be extracted: the file was only partly read."""
        if message not in self.incomplete:
            self.incomplete.append(message)


Extractor = Callable[[str, Report, Limits], Iterator[Segment]]
Sink = Callable[[Segment], None]


@dataclass
class ExtractionResult:
    status: ExtractionStatus
    reason: str = ""  # why the status is not SUCCEEDED - fixed text
    stats: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"status": self.status.value, "reason": self.reason, "stats": self.stats, "notes": self.notes}


UNREADABLE = "The file could not be read. It may be damaged or use a structure PrivGuard does not handle."
MISSING = "The stored copy of this file could not be found."


def run_extractor(extractor: Extractor, path: str, limits: Limits, sink: Sink | None = None) -> ExtractionResult:
    """Drive one extractor over one file and decide its status (FR-028).

    Exceptions raised BY THE EXTRACTOR become a status. Exceptions raised by
    the sink - the consumer, such as Cycle 5's detectors - propagate: a bug in
    detection is not a damaged file and must not be reported as one.
    """
    report = Report()
    segments = characters = 0
    failure: tuple[ExtractionStatus, str] | None = None
    iterator = extractor(path, report, limits)
    try:
        while True:
            try:
                segment = next(iterator)
            except StopIteration:
                break
            except NotSupported as exc:
                failure = (ExtractionStatus.NOT_SUPPORTED, str(exc))
                break
            except ExtractionError as exc:
                failure = (ExtractionStatus.FAILED, str(exc))
                break
            except FileNotFoundError:
                failure = (ExtractionStatus.FAILED, MISSING)
                break
            except Exception as exc:
                # Never report the exception's own text: it can quote the file's content.
                logger.warning("Extractor %s raised %s", getattr(extractor, "__name__", "?"), type(exc).__name__)
                failure = (ExtractionStatus.FAILED, UNREADABLE)
                break

            if characters + len(segment.text) > limits.max_chars:
                report.partial(f"Extraction stopped after {limits.max_chars:,} characters, the per-file limit.")
                break
            characters += len(segment.text)
            segments += 1
            if sink is not None:
                sink(segment)  # outside the try: consumer errors propagate
    finally:
        iterator.close()  # lets the extractor's `with` blocks close files after an early stop

    stats = {"segments": segments, "characters": characters, **report.stats}
    if failure is not None:
        status, reason = failure
        if segments:  # something was read before the problem
            status = ExtractionStatus.PARTIAL
        return ExtractionResult(status, " ".join([reason, *report.incomplete]), stats, report.notes)
    if report.incomplete:
        return ExtractionResult(ExtractionStatus.PARTIAL, " ".join(report.incomplete), stats, report.notes)
    if segments == 0:
        report.note("No text was found in this file.")
    return ExtractionResult(ExtractionStatus.SUCCEEDED, "", stats, report.notes)
