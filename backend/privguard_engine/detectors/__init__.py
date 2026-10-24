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
    CATEGORY_OF, CHECKSUM, CONTEXT, DETECTION_VERSION, ENTROPY, PATTERN, TYPE_LABELS, VALIDATED,
    Detection, DetectionConfig, Detector, Finding,
)
from .collector import FindingCollector, resolve_overlaps
from .contact import detect_emails, detect_phones
from .financial import (
    detect_gstins, detect_ibans, detect_ifsc, detect_labelled_financial, detect_payment_cards, detect_upi_ids,
    gstin_check_character, iban_valid, luhn_check_digit, luhn_valid,
)
from .india import detect_aadhaar, detect_pan, verhoeff_check_digit, verhoeff_valid
from .labelled import detect_addresses, detect_dates_of_birth, detect_person_names, detect_record_fields
from .secrets import (
    detect_assignments, detect_auth_headers, detect_connection_strings, detect_jwts, detect_known_secrets,
    detect_private_keys,
)

# Name -> detector. The names are what DetectionConfig.enabled refers to.
DETECTORS: dict[str, Detector] = {
    # personal data (Cycle 5)
    "email": detect_emails,
    "phone": detect_phones,
    "aadhaar": detect_aadhaar,
    "pan": detect_pan,
    "date_of_birth": detect_dates_of_birth,
    "person_name": detect_person_names,
    "record_fields": detect_record_fields,
    "address": detect_addresses,
    # secrets and credentials (Cycle 6)
    "private_key": detect_private_keys,
    "known_tokens": detect_known_secrets,
    "jwt": detect_jwts,
    "connection_string": detect_connection_strings,
    "auth_header": detect_auth_headers,
    "config_secrets": detect_assignments,
    # financial information (Cycle 6)
    "payment_card": detect_payment_cards,
    "iban": detect_ibans,
    "gstin": detect_gstins,
    "ifsc": detect_ifsc,
    "upi": detect_upi_ids,
    "financial_fields": detect_labelled_financial,
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
    "CATEGORY_OF", "CHECKSUM", "CONTEXT", "DETECTION_VERSION", "DETECTORS", "ENTROPY", "PATTERN", "TYPE_LABELS",
    "VALIDATED",
    "Detection", "DetectionConfig", "Finding", "FindingCollector",
    "detect_segment", "gstin_check_character", "iban_valid", "luhn_check_digit", "luhn_valid",
    "verhoeff_check_digit", "verhoeff_valid",
]
