"""See what PrivGuard extracts from a LOCAL file - for learning and debugging.

    cd backend
    .venv/Scripts/python.exe -m privguard_engine.extractors ../samples/extraction-demo/letter.docx

Runs intake (is the file what it claims to be?) and then extraction, and
prints each segment with its location. It prints the file's TEXT, so use it on
synthetic files such as samples/. It never touches the database or uploads.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..intake import Verdict, inspect_file
from . import Limits, extract_file
from .ocr import OcrConfig


def _location(location) -> str:
    return ", ".join(f"{key}={value}" for key, value in location.items())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m privguard_engine.extractors", description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path, help="a local file to extract")
    parser.add_argument("--max", type=int, default=40, help="segments to print (default: 40)")
    parser.add_argument("--tesseract", metavar="PATH",
                        help="tesseract.exe, to read images and scanned PDF pages (Cycle 8); OCR is off without it")
    args = parser.parse_args(argv)
    ocr = OcrConfig(command=args.tesseract) if args.tesseract else None

    # When output is piped (Git Bash, VS Code tasks), Windows Python defaults to
    # the legacy cp1252 code page, which a UTF-8 terminal shows as "�". Always
    # write UTF-8, and never crash on a character that can't be shown.
    if hasattr(sys.stdout, "reconfigure"):  # absent when output is captured, e.g. in tests
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

    size = args.path.stat().st_size
    with args.path.open("rb") as stream:
        inspection = inspect_file(args.path.name, stream, size, max_bytes=max(size, 1), ocr=ocr is not None)
    print(f"{args.path.name}: {inspection.verdict.value} as '{inspection.file_type or 'unknown'}'"
          + (f" - {inspection.reason}" if inspection.reason else ""))
    if inspection.verdict is not Verdict.SUPPORTED:
        return 1

    shown = 0

    def show(segment) -> None:
        nonlocal shown
        if shown < args.max:
            text = segment.text.replace("\n", " / ")
            print(f"  [{_location(segment.location)}] {text[:100]}{'...' if len(text) > 100 else ''}")
        shown += 1

    result = extract_file(str(args.path), inspection.file_type, limits=Limits(ocr=ocr), sink=show)
    if shown > args.max:
        print(f"  ... and {shown - args.max} more segments")
    print(f"result: {result.status.value}" + (f" - {result.reason}" if result.reason else ""))
    print(f"stats:  {result.stats}")
    for note in result.notes:
        print(f"note:   {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
