"""Detection inside the extraction child: segments in, masked Findings out (FR-053, FR-078, FR-085).

FindingCollector is the "sink" Cycle 4's extract_file() feeds segments into.
Raw values exist only inside this object, inside the isolated child process.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

from .base import PERSONAL, Detection, DetectionConfig, Finding
from .contact import country_code_of
from .masking import keep_ends, mask_aadhaar, mask_email, mask_name, mask_phone, mask_text, sanitise_preview

# How each type is masked. Enough to recognise a finding, never enough to reuse it.
_MASKERS = {
    "email_address": lambda d: mask_email(d.value),
    "phone_number": lambda d: mask_phone(d.value, country_code_of(d.key)),
    "aadhaar_number": lambda d: mask_aadhaar(d.value),
    "pan_number": lambda d: keep_ends(d.value, end=4),
    "date_of_birth": lambda d: keep_ends(d.value),
    "person_name": lambda d: mask_name(d.value),
    "postal_address": lambda d: mask_text(d.value, keep=2),
    "postal_code": lambda d: keep_ends(d.value, start=2),
    # Values from a short list ("Female", "B+", "Hindu"): one visible letter - or
    # even the length - gives the value away, so these are hidden completely.
    **dict.fromkeys(("gender", "blood_group", "religion_or_caste", "marital_status", "nationality"),
                    lambda d: "****"),
}

# Location keys worth keeping. "header" is deliberately dropped: in a CSV with
# no header row, the "header" is really the first row of DATA - a real name
# could otherwise be stored unmasked inside a location (FR-115, NFR-025).
STORED_LOCATION_KEYS = ("sheet", "cell", "row", "column", "line", "page", "slide", "part", "paragraph",
                        "kind", "field", "hidden")
# A hostile file can make a match as long as it likes ("Mr " + 10,000 letters).
# Capping the mask also bounds every preview built around it.
MAX_MASKED_LENGTH = 100


def mask(detection: Detection) -> str:
    masked = _MASKERS.get(detection.type, lambda d: mask_text(d.value, keep=1))(detection)
    return masked if len(masked) <= MAX_MASKED_LENGTH else masked[:MAX_MASKED_LENGTH - 1] + "…"


def safe_location(location: Mapping) -> dict:
    return {key: location[key] for key in STORED_LOCATION_KEYS if key in location}


def resolve_overlaps(detections: list[Detection]) -> list[Detection]:
    """Where detections overlap, keep the most confident (ties: the longer span).

    Characters already claimed are marked in a bytearray, so checking a
    detection costs the length of its match - not the number of detections kept
    so far. Comparing every pair was quadratic: one hostile 1 MB line yields
    ~166,000 detections, which would have taken about 11 minutes (measured).
    """
    if len(detections) < 2:
        return list(detections)
    taken = bytearray(max(d.end for d in detections))
    chosen: list[Detection] = []
    for d in sorted(detections, key=lambda d: (-d.confidence, -(d.end - d.start), d.start)):
        if taken.find(1, d.start, d.end) == -1:
            taken[d.start:d.end] = b"\x01" * (d.end - d.start)
            chosen.append(d)
    return sorted(chosen, key=lambda d: d.start)


def mask_segment(text: str, detections: list[Detection]) -> tuple[str, list[tuple[int, int]]]:
    """Mask EVERY detection in a segment, and every leftover run of 4+ digits.

    Previews are cut from this masked text, so a preview for one finding can
    never reveal a neighbouring value (FR-085).
    Returns the masked text and each detection's span within it.
    """
    pieces, spans, length, position = [], [], 0, 0
    for detection in detections:
        gap = sanitise_preview(text[position:detection.start])
        masked = mask(detection)
        pieces += [gap, masked]
        spans.append((length + len(gap), length + len(gap) + len(masked)))
        length += len(gap) + len(masked)
        position = detection.end
    pieces.append(sanitise_preview(text[position:]))
    return "".join(pieces), spans


class _Group:
    """Every occurrence of one value, of one type, in one file.

    The finding shows its MOST confident occurrence: that occurrence's masked
    value, preview and explanation, with its location first - so an explanation
    such as "labelled 'mobile'" always describes the preview beside it.
    """

    def __init__(self):
        self.best: Detection | None = None
        self.masked = self.preview = ""
        self.locations: list[dict] = []
        self.occurrences = 0

    def add(self, detection: Detection, location: dict, max_locations: int, show) -> None:
        self.occurrences += 1
        if self.best is None or detection.confidence > self.best.confidence:
            self.best = detection
            self.masked, self.preview = show()  # only computed when it will be shown
            if location in self.locations:
                self.locations.remove(location)
            self.locations.insert(0, location)
            del self.locations[max_locations:]
        elif len(self.locations) < max_locations and location not in self.locations:
            self.locations.append(location)


class FindingCollector:
    """Feed it segments (it is an extraction sink); ask it for findings()."""

    def __init__(self, config: DetectionConfig | None = None, *, max_findings: int = 5_000,
                 max_locations: int = 20, preview_radius: int = 40):
        from . import detect_segment  # the registry imports this module, so import late

        self._detect = detect_segment
        self.config = config or DetectionConfig()
        self.max_findings, self.max_locations, self.radius = max_findings, max_locations, preview_radius
        self._groups: dict[tuple[str, str], _Group] = {}
        self.detections = 0
        self.truncated = False

    def __call__(self, segment) -> None:
        detections = self._detect(segment.text, segment.location, self.config)
        if not detections:
            return
        masked_text, spans = mask_segment(segment.text, detections)
        location = safe_location(segment.location)
        for detection, (start, end) in zip(detections, spans):
            self.detections += 1
            key = (detection.type, detection.key)
            group = self._groups.get(key)
            if group is None:
                if len(self._groups) >= self.max_findings:
                    self.truncated = True
                    continue
                group = self._groups[key] = _Group()
            # add() calls this at once or not at all, so start/end are this detection's.
            group.add(detection, location, self.max_locations,
                      lambda: (masked_text[start:end], self._preview(masked_text, start, end)))

    def _preview(self, text: str, start: int, end: int) -> str:
        left, right = max(0, start - self.radius), min(len(text), end + self.radius)
        preview = text[left:right].replace("\r", " ").replace("\n", " / ")
        return ("…" if left else "") + preview.strip() + ("…" if right < len(text) else "")

    def findings(self) -> list[Finding]:
        return [
            Finding(
                category=PERSONAL, type=g.best.type, method=g.best.method, confidence=g.best.confidence,
                masked_value=g.masked, context=g.preview, location=g.locations[0],
                more_locations=tuple(g.locations[1:]), occurrences=g.occurrences, explanation=g.best.explanation,
            )
            for g in self._groups.values()
        ]

    def stats(self) -> dict:
        by_type = Counter(g.best.type for g in self._groups.values())
        return {"detections": self.detections, "findings": len(self._groups),
                "by_type": dict(by_type), "truncated": self.truncated}
