"""CSV and TSV: one segment per non-empty cell, located by row, column and header (FR-025, FR-029).

The header matters for Cycle 5: "0791 123 456" under a column called "phone"
is far more convincing than the same digits under "order id" (FR-038, FR-044).
"""

from __future__ import annotations

import csv

from .base import ExtractionError, Limits, Report, Segment
from .text import text_encoding

_SNIFF_CHARS = 64 * 1024
_DELIMITERS = {",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe"}
# The stdlib default (128 KB per field) is low for exports that embed blobs.
_FIELD_LIMIT = 1024 * 1024


def _dialect(sample: str):
    try:
        return csv.Sniffer().sniff(sample, delimiters="".join(_DELIMITERS))
    except csv.Error:
        return csv.excel  # plain comma-separated


def extract_delimited(path: str, report: Report, limits: Limits):
    codec = text_encoding(path, report)
    with open(path, "r", encoding=codec, errors="replace", newline="") as stream:
        dialect = _dialect(stream.read(_SNIFF_CHARS))
    report.set("delimiter", _DELIMITERS.get(dialect.delimiter, "other"))

    previous_limit = csv.field_size_limit(_FIELD_LIMIT)  # process-wide; restored below
    try:
        # newline="" is required by the csv module so quoted fields may contain line breaks.
        with open(path, "r", encoding=codec, errors="replace", newline="") as stream:
            reader = csv.reader(stream, dialect)
            headers: list[str] | None = None
            header_row = 0
            first_line = 1  # a row can span several lines; report where it STARTS
            cells = 0
            row_number = 0
            try:
                for row_number, row in enumerate(reader, start=1):
                    report.count("rows")
                    if headers is None and any(value.strip() for value in row):
                        headers, header_row = [value.strip() for value in row], row_number
                    for column, value in enumerate(row, start=1):
                        if not value.strip():
                            continue
                        cells += 1
                        if cells > limits.max_cells:
                            report.partial(f"Only the first {limits.max_cells:,} cells were read (the per-file cell limit).")
                            return
                        location = {"row": row_number, "column": column, "line": first_line}
                        if row_number > header_row and column <= len(headers) and headers[column - 1]:
                            location["header"] = headers[column - 1]
                        yield Segment(value, location)
                    first_line = reader.line_num + 1
            except csv.Error:
                raise ExtractionError(
                    f"The file stopped parsing as CSV after row {row_number}; the rest was not read."
                ) from None
            report.set("cells", cells)
    finally:
        csv.field_size_limit(previous_limit)
