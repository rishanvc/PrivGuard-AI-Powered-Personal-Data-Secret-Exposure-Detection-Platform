"""Context: the words just before a value, and the column it sits in (FR-038, FR-044).

The same ten digits are a phone number under a column called "Mobile" and an
order reference under "Invoice". Context is how detectors tell them apart.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_SEPARATORS = re.compile(r"[\s_\-./:#()\[\]\"'=,;]+")


def normalise(label: str) -> str:
    """'customerName', 'Customer_Name', ' CUSTOMER NAME: ' -> 'customer name'."""
    return _SEPARATORS.sub(" ", _CAMEL.sub(" ", label)).strip().lower()


def phrase_in(text: str, phrases: Iterable[str]) -> str | None:
    """The first phrase that appears in already-normalised text as whole words."""
    for phrase in phrases:
        if re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text):
            return phrase
    return None


def label_before(text: str, start: int, phrases: Iterable[str], window: int = 40) -> str | None:
    """A context phrase in the `window` characters just before a match.

    Works for prose ("Mobile: 98765 43210"), key=value lines (mobile=...) and
    JSON ("mobile": "...") alike, because punctuation is normalised away.
    """
    return phrase_in(normalise(text[max(0, start - window):start]), phrases)


def header_mentions(location: Mapping, phrases: Iterable[str]) -> str | None:
    """A context phrase anywhere in the column header ('Work Email' mentions 'email')."""
    header = normalise(str(location.get("header") or ""))
    return phrase_in(header, phrases) if header else None


def header_is(location: Mapping, phrases: Iterable[str]) -> str | None:
    """The column header IS one of the phrases. Stricter than header_mentions:
    'File name' must not count as a person's-name column just because it ends in 'name'."""
    header = normalise(str(location.get("header") or ""))
    return header if header in phrases else None
