"""See what PrivGuard detects in a LOCAL file - for learning and debugging.

    cd backend
    .venv/Scripts/python.exe -m privguard_engine.detectors ../samples/extraction-demo/staff.xlsx

Runs intake, extraction and detection, and prints each finding exactly as it
would be stored: masked value, masked preview, location, method, confidence.
It never prints the file's text, and never touches the database or uploads.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..extractors import extract_file
from ..intake import Verdict, inspect_file
from . import TYPE_LABELS, DetectionConfig, FindingCollector


def _location(location) -> str:
    return ", ".join(f"{key}={value}" for key, value in location.items()) or "-"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m privguard_engine.detectors", description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path, help="a local file to scan")
    parser.add_argument("--region", default="IN", help="region for phone numbers without a country code (default: IN)")
    parser.add_argument("--max", type=int, default=40, help="findings to print (default: 40)")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):  # see privguard_engine.extractors.__main__
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

    size = args.path.stat().st_size
    with args.path.open("rb") as stream:
        inspection = inspect_file(args.path.name, stream, size, max_bytes=max(size, 1))
    print(f"{args.path.name}: {inspection.verdict.value} as '{inspection.file_type or 'unknown'}'"
          + (f" - {inspection.reason}" if inspection.reason else ""))
    if inspection.verdict is not Verdict.SUPPORTED:
        return 1

    collector = FindingCollector(DetectionConfig(region=args.region.upper()))
    result = extract_file(str(args.path), inspection.file_type, sink=collector)
    print(f"extraction: {result.status.value}" + (f" - {result.reason}" if result.reason else ""))

    findings = sorted(collector.findings(), key=lambda f: (-f.confidence, f.type))
    for finding in findings[:args.max]:
        repeats = f", {finding.occurrences} occurrences" if finding.occurrences > 1 else ""
        print(f"\n  {TYPE_LABELS.get(finding.type, finding.type)}: {finding.masked_value}"
              f"   [{finding.method}, confidence {finding.confidence:.2f}{repeats}]")
        print(f"    at       {_location(finding.location)}"
              + (f" (+{len(finding.more_locations)} more)" if finding.more_locations else ""))
        print(f"    preview  {finding.context}")
        print(f"    why      {finding.explanation}")
    if len(findings) > args.max:
        print(f"\n  ... and {len(findings) - args.max} more findings")
    print(f"\nstats: {collector.stats()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
