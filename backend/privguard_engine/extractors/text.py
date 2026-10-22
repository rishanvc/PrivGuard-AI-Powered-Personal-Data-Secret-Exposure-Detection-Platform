"""Plain text, source code, configuration, JSON, YAML, XML, .env and key files (FR-020, FR-021).

Read as lines and deliberately NOT parsed. A parser is attack surface (YAML
loaders that construct objects, XML entities), and editors number lines the
same way this module does, so a location is exactly what a developer sees.
"""

from __future__ import annotations

import codecs

from .base import Limits, Report, Segment

# UTF-32 LE must be tested before UTF-16 LE: its BOM starts with the same bytes.
_BOMS = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)
_CHUNK = 1024 * 1024
_FALLBACK = "cp1252"


def detect_encoding(path: str) -> tuple[str, bool]:
    """Return (codec, used_fallback): a byte-order mark, else strict UTF-8, else Windows-1252.

    Validates UTF-8 across the WHOLE file in chunks - a file that is valid for
    its first megabyte can still contain a Windows-1252 byte further on.
    """
    with open(path, "rb") as stream:
        head = stream.read(4)
        for bom, codec in _BOMS:
            if head.startswith(bom):
                return codec, False
        stream.seek(0)
        decoder = codecs.getincrementaldecoder("utf-8")("strict")
        try:
            while chunk := stream.read(_CHUNK):
                decoder.decode(chunk)
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            return _FALLBACK, True
    return "utf-8", False


def text_encoding(path: str, report: Report) -> str:
    """Detect the encoding and record it (and any fallback) on the report."""
    codec, fallback = detect_encoding(path)
    report.set("encoding", "windows-1252" if fallback else codec)
    if fallback:
        report.note(
            "The file is not valid UTF-8, so it was read as Windows-1252; "
            "a few characters may display incorrectly."
        )
    return codec


def extract_text(path: str, report: Report, limits: Limits):
    codec = text_encoding(path, report)
    # newline=None: "\r\n", "\n" and a lone "\r" all end a line, as in editors.
    # errors="replace" only matters for the fallback, where five byte values are undefined.
    with open(path, "r", encoding=codec, errors="replace", newline=None) as stream:
        for number, line in enumerate(stream, start=1):
            report.count("lines")
            text = line.rstrip("\n")
            if text.strip():
                yield Segment(text, {"line": number})
