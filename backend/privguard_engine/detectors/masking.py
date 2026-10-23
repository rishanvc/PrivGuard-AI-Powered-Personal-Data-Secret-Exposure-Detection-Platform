"""Masking: what a finding may show of the value it found (FR-045, FR-053, NFR-014).

Enough to recognise and investigate a finding, never enough to reuse the value.
"""

from __future__ import annotations

import re

_DIGIT_RUN = re.compile(r"\d{4,}")


def keep_ends(value: str, *, start: int = 0, end: int = 0, char: str = "*") -> str:
    """Mask letters and digits, keeping `start` of them at the front and `end` at the
    back. Separators (spaces, dashes, dots) stay, so the shape remains readable."""
    positions = [i for i, ch in enumerate(value) if ch.isalnum()]
    keep = set(positions[:start]) | set(positions[len(positions) - end:] if end else [])
    return "".join(ch if (i in keep or not ch.isalnum()) else char for i, ch in enumerate(value))


def mask_email(value: str) -> str:
    local, _, domain = value.partition("@")
    return f"{local[:1]}***@{domain}"  # the domain helps triage (internal vs external)


def mask_phone(value: str, country_code: str = "") -> str:
    """'+44 20 7946 0001' -> '+44 ** **** **01'."""
    keep_front = len(country_code) if value.lstrip().startswith("+") else 0
    return keep_ends(value, start=keep_front, end=2)


def mask_aadhaar(value: str) -> str:
    """UIDAI's own masked-Aadhaar convention: only the last four digits."""
    digits = re.sub(r"\D", "", value)
    return f"XXXX XXXX {digits[-4:]}"


def mask_name(value: str) -> str:
    """'Ana Example' -> 'A** E******'."""
    return " ".join(word[:1] + "*" * (len(word) - 1) for word in value.split())


def mask_digits(value: str) -> str:
    return re.sub(r"\d", "*", value)


def mask_text(value: str, *, keep: int = 1, limit: int = 32) -> str:
    masked = keep_ends(value, start=keep)
    return masked if len(masked) <= limit else masked[: limit - 1] + "…"


def sanitise_preview(text: str) -> str:
    """Mask every run of 4+ digits in text that no detector claimed.

    Defence in depth for previews: a number we failed to recognise as
    sensitive should still not be stored in full beside a finding.
    """
    return _DIGIT_RUN.sub(lambda m: "*" * len(m.group()), text)
