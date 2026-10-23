"""Detection: turn extracted segments into masked findings (FR-031 to FR-039).

Framework-free (D-002). Runs inside the extraction child, so raw values never
leave that process:

    collector = FindingCollector()
    extract_file(path, "xlsx", sink=collector)
    collector.findings()        # masked values, masked previews, locations

To see what is found in a LOCAL file (prints masked values only):

    python -m privguard_engine.detectors ../samples/extraction-demo/staff.xlsx
"""

from __future__ import annotations

from collections.abc import Mapping

from .base import (
    CHECKSUM, CONTEXT, DETECTION_VERSION, PATTERN, TYPE_LABELS, VALIDATED,
    Detection, DetectionConfig, Detector, Finding,
)
from .collector import FindingCollector, resolve_overlaps
from .contact import detect_emails, detect_phones
from .india import detect_aadhaar, detect_pan, verhoeff_check_digit, verhoeff_valid
from .labelled import detect_addresses, detect_dates_of_birth, detect_person_names, detect_record_fields

# Name -> detector. The names are what DetectionConfig.enabled refers to.
DETECTORS: dict[str, Detector] = {
    "email": detect_emails,
    "phone": detect_phones,
    "aadhaar": detect_aadhaar,
    "pan": detect_pan,
    "date_of_birth": detect_dates_of_birth,
    "person_name": detect_person_names,
    "record_fields": detect_record_fields,
    "address": detect_addresses,
}


def detect_segment(text: str, location: Mapping, config: DetectionConfig | None = None) -> list[Detection]:
    """Every enabled detector's findings for one segment, overlaps resolved."""
    config = config or DetectionConfig()
    found: list[Detection] = []
    for name, detector in DETECTORS.items():
        if config.enabled is None or name in config.enabled:
            found.extend(detector(text, location, config))
    return resolve_overlaps(found)


__all__ = [
    "CHECKSUM", "CONTEXT", "DETECTION_VERSION", "DETECTORS", "PATTERN", "TYPE_LABELS", "VALIDATED",
    "Detection", "DetectionConfig", "Finding", "FindingCollector",
    "detect_segment", "verhoeff_check_digit", "verhoeff_valid",
]
