"""Search, filters and sorting for findings (FR-079, FR-083, FR-087, FR-088).

Written by hand: six filters, a search box and five orderings are about sixty
lines, and do not justify a dependency (django-filter). Every value is checked
against a fixed list, so a typo is a clear 400 - never a silently empty list.

Search covers what IS stored: file paths, kinds of finding, masked values and
explanations. Raw values were never stored, so they cannot be searched (D-032).
"""

from __future__ import annotations

import uuid

from django.db.models import Case, IntegerField, Q, QuerySet, Value, When
from rest_framework.exceptions import ValidationError

from privguard_engine.detectors import CHECKSUM, CONTEXT, ENTROPY, PATTERN, TYPE_LABELS, VALIDATED
from privguard_engine.extractors import EXTRACTORS
from privguard_engine.risk import LEVELS

from .models import Finding

NOT_ASSESSED = "not_assessed"
MAX_SEARCH = 100

# Severity is stored as text, and alphabetical order would be critical, high,
# informational, low, medium - Medium last. So sort by a rank computed in the
# database. Not-assessed findings (before Cycle 6) come last.
SEVERITY_RANK = Case(
    *[When(severity=level, then=Value(rank)) for rank, level in enumerate(LEVELS)],
    default=Value(len(LEVELS)), output_field=IntegerField(),
)
ORDERINGS = {
    "severity": ("severity_rank", "-confidence", "scanned_file__relative_path", "subcategory"),
    "risk": ("-risk_score", "severity_rank", "scanned_file__relative_path"),
    "category": ("category", "severity_rank", "-confidence"),
    "file": ("scanned_file__relative_path", "severity_rank", "-confidence"),
    "confidence": ("-confidence", "severity_rank", "scanned_file__relative_path"),
}

# parameter -> (database field, allowed values)
_CHOICES = {
    "severity": ("severity", (*LEVELS, NOT_ASSESSED)),
    "category": ("category", tuple(Finding.Category.values)),
    "file_type": ("scanned_file__file_type", tuple(sorted(EXTRACTORS))),
    "method": ("detection_method", (PATTERN, VALIDATED, CHECKSUM, CONTEXT, ENTROPY)),
    "status": ("review_status", tuple(Finding.ReviewStatus.values)),
}


def _values(params, name: str) -> list[str]:
    return [value.strip() for value in params.get(name, "").split(",") if value.strip()]


def apply(queryset: QuerySet, params) -> QuerySet:
    """Filter, search and order findings from query parameters. Raises ValidationError (400)."""
    errors = {}

    scans = _values(params, "scan")
    if scans:
        try:
            queryset = queryset.filter(scan_id__in=[uuid.UUID(value) for value in scans])
        except ValueError:
            errors["scan"] = "Scan IDs must be UUIDs."

    for name, (field, allowed) in _CHOICES.items():
        values = _values(params, name)
        if not values:
            continue
        unknown = [value for value in values if value not in allowed]
        if unknown:
            errors[name] = f"Unknown value {unknown[0]!r}. Choose from: {', '.join(allowed)}."
            continue
        condition = Q(**{f"{field}__in": [v for v in values if v != NOT_ASSESSED]})
        if NOT_ASSESSED in values:
            condition |= Q(severity__isnull=True)
        queryset = queryset.filter(condition)

    search = params.get("q", "").strip()
    if len(search) > MAX_SEARCH:
        errors["q"] = f"Search for at most {MAX_SEARCH} characters."
    elif search:
        kinds = [kind for kind, label in TYPE_LABELS.items() if search.casefold() in label.casefold()]
        queryset = queryset.filter(
            Q(scanned_file__relative_path__icontains=search) | Q(masked_value__icontains=search)
            | Q(description__icontains=search) | Q(subcategory__icontains=search) | Q(subcategory__in=kinds)
        )

    ordering = params.get("ordering", "severity")
    if ordering not in ORDERINGS:
        errors["ordering"] = f"Choose one of: {', '.join(ORDERINGS)}."

    if errors:
        raise ValidationError(errors)
    return queryset.annotate(severity_rank=SEVERITY_RANK).order_by(*ORDERINGS[ordering], "created_at", "id")
