"""Masking: what a finding may show of the value it found (FR-045, FR-053, NFR-014).

Enough to recognise and investigate a finding, never enough to reuse the value.
"""

from __future__ import annotations

import math
import re
from collections import Counter

_DIGIT_RUN = re.compile(r"\d{4,}")
_TOKEN_RUN = re.compile(r"[A-Za-z0-9+/=_\-]{20,}")


def shannon_entropy(text: str) -> float:
    """Average bits per character, from how often each character occurs.

    "aaaa" -> 0.0; English words -> about 2-3; a random base64 key -> 5-6.
    A string of length n can never exceed log2(n), so short strings score low.
    """
    if not text:
        return 0.0
    total = len(text)
    return -sum(n / total * math.log2(n / total) for n in Counter(text).values())


def looks_random(token: str) -> bool:
    """Upper case, lower case and digits mixed - or simply very high entropy."""
    mixed = any(c.isupper() for c in token) and any(c.islower() for c in token) and any(c.isdigit() for c in token)
    return mixed or shannon_entropy(token) >= 4.2


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
    """Mask, in text that no detector claimed, every run of 4+ digits and
    every long random-looking token (Cycle 6).

    Defence in depth for previews: a number or a key in a format we failed to
    recognise should still not be stored in full beside a finding.
    """
    text = _TOKEN_RUN.sub(lambda m: "*" * len(m.group()) if looks_random(m.group()) else m.group(), text)
    return _DIGIT_RUN.sub(lambda m: "*" * len(m.group()), text)
