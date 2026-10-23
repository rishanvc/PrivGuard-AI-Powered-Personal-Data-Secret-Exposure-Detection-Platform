"""Indian government identifiers: Aadhaar and PAN (FR-036; Cycle 5 region decision: India)."""

from __future__ import annotations

import re

from .base import CHECKSUM, PATTERN, Detection, DetectionConfig
from .context import header_mentions, label_before

# ------------------------------------------------------------------ Verhoeff

# Verhoeff (1969): catches EVERY single-digit error and EVERY swap of adjacent
# digits - the mistakes people make when copying numbers. Aadhaar's last digit
# is a Verhoeff check digit, so a random 12-digit number passes 1 time in 10.
_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 2, 3, 4, 0, 6, 7, 8, 9, 5), (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7), (4, 0, 1, 2, 3, 9, 5, 6, 7, 8), (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2), (7, 6, 5, 9, 8, 2, 1, 0, 4, 3), (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 5, 7, 6, 2, 8, 3, 0, 9, 4), (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7), (9, 4, 5, 3, 1, 2, 6, 8, 7, 0), (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5), (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def verhoeff_valid(digits: str) -> bool:
    check = 0
    for i, digit in enumerate(reversed(digits)):
        check = _D[check][_P[i % 8][int(digit)]]
    return check == 0


def verhoeff_check_digit(digits: str) -> str:
    """The digit to append so the result is Verhoeff-valid (used to build test data)."""
    check = 0
    for i, digit in enumerate(reversed(digits)):
        check = _D[check][_P[(i + 1) % 8][int(digit)]]
    return str(_INV[check])


# ------------------------------------------------------------------ Aadhaar

# Twelve digits, first digit 2-9, optionally grouped 4-4-4 with ONE consistent
# separator (\2). The look-arounds refuse to match inside a longer number,
# such as a 16-digit card written in groups of four.
_AADHAAR = re.compile(r"(?<!\d)(?<!\d[ -])([2-9]\d{3})([ -]?)(\d{4})\2(\d{4})(?![ -]?\d)")
_AADHAAR_CONTEXT = ("aadhaar", "aadhar", "adhaar", "uid", "uidai", "aadhaar no", "aadhaar number")


def detect_aadhaar(text: str, location, config: DetectionConfig):
    for match in _AADHAAR.finditer(text):
        digits = match.group(1) + match.group(3) + match.group(4)
        if not verhoeff_valid(digits):
            continue
        grouped = bool(match.group(2))
        context = header_mentions(location, _AADHAAR_CONTEXT) or label_before(text, match.start(), _AADHAAR_CONTEXT)
        if not (grouped or context):
            # Bare and unlabelled: 1 in 10 order numbers would pass the checksum too.
            continue
        reasons = ["12 digits with a valid Verhoeff checksum, the check Aadhaar numbers use"]
        if context:
            reasons.append(f"labelled '{context}'")
            confidence = 0.95
        else:
            reasons.append("written in Aadhaar's usual 4-4-4 grouping")
            confidence = 0.8
        yield Detection("aadhaar_number", match.start(), match.end(), match.group(), digits,
                        CHECKSUM, confidence, "; ".join(reasons) + ".")


# ------------------------------------------------------------------ PAN

# 5 letters, 4 digits, 1 letter. The 4th letter is the holder type.
_PAN = re.compile(r"(?<![A-Z0-9])([A-Z]{3}([ABCFGHJLPT])[A-Z][0-9]{4}[A-Z])(?![A-Z0-9])")
_HOLDERS = {
    "P": "an individual", "C": "a company", "H": "a Hindu undivided family", "F": "a firm",
    "A": "an association of persons", "T": "a trust", "B": "a body of individuals",
    "L": "a local authority", "J": "an artificial juridical person", "G": "a government body",
}
_PAN_CONTEXT = ("pan", "pan no", "pan number", "permanent account number", "income tax", "pan card")


def detect_pan(text: str, location, config: DetectionConfig):
    for match in _PAN.finditer(text):
        context = header_mentions(location, _PAN_CONTEXT) or label_before(text, match.start(), _PAN_CONTEXT)
        reasons = [
            f"Matches the PAN format; its 4th letter marks it as belonging to {_HOLDERS[match.group(2)]}",
            "PAN's final letter is a check character, but its algorithm is not public, so only the format is verified",
        ]
        if context:
            reasons.append(f"labelled '{context}'")
        yield Detection("pan_number", match.start(), match.end(), match.group(1), match.group(1),
                        PATTERN, 0.95 if context else 0.75, "; ".join(reasons) + ".")
