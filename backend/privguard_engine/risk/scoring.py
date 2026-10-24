"""Risk scores, 0-100 (FR-074 to FR-077, FR-080, SRS 8.3). Versioned, tested, explained.

Severity says what KIND of danger a finding is. Risk adds how sure we are,
how often it appears, and whether it sits where people do not look.

    finding risk = severity base x confidence factor + repeats + overlooked content   (capped at 100)
    scan risk    = the riskiest counted finding + 3 for each other serious one          (bonus at most 15)

The scan score is never a sum: a thousand e-mail addresses must not outrank
one leaked private key (SRS 8.3). Findings reviewed as false positive or
resolved do not count (Cycle 7 decision).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .severity import CRITICAL, HIGH, INFORMATIONAL, LEVEL_LABELS, LOW, MEDIUM

# Bump whenever a number below changes: each scan records the version that scored it.
RISK_POLICY_VERSION = 1

BASE = {CRITICAL: 90, HIGH: 70, MEDIUM: 45, LOW: 20, INFORMATIONAL: 5}
REPEATS_MAX = 10          # 2 occurrences +3, 4 +6, 8 +9, 16 or more +10
OVERLOOKED_BONUS = 5      # tracked deletions, hidden sheets, comments, speaker notes, document properties
SERIOUS = 60              # a finding at or above this counts towards the scan's breadth bonus
BONUS_EACH, BONUS_MAX = 3, 15
NOT_COUNTED = frozenset({"false_positive", "resolved"})  # review statuses left out of the scan score

# FR-077: the default interpretation. Lowest score of each band, highest band first.
BANDS = ((70, "critical", "Critical"), (40, "high", "High"), (20, "moderate", "Moderate"), (0, "low", "Low"))
LIMITATION = ("This score is an assessment of the evidence PrivGuard detected. It is not proof that the files "
              "are safe or unsafe, and it does not cover content PrivGuard could not read.")

_OVERLOOKED_PARTS = {"comments": "a comment", "notes": "speaker notes", "properties": "document properties"}
_OVERLOOKED_KINDS = {"deleted": "a tracked deletion", "field code": "a field code"}


@dataclass(frozen=True)
class Score:
    value: int
    factors: tuple[str, ...]  # fixed wording - never text from a file


def _overlooked(locations: Iterable[Mapping]) -> str | None:
    """Where people do not look, but the file still carries it (FR-099)."""
    for location in locations:
        if location.get("kind") in _OVERLOOKED_KINDS:
            return _OVERLOOKED_KINDS[location["kind"]]
        if location.get("hidden"):
            return "a hidden sheet"
        if location.get("part") in _OVERLOOKED_PARTS:
            return _OVERLOOKED_PARTS[location["part"]]
    return None


def finding_risk(severity: str, confidence: float, occurrences: int, locations: Iterable[Mapping]) -> Score:
    base = BASE[severity]
    factor = 0.6 + 0.4 * confidence  # confidence 1.0 keeps the base; 0.4 takes it to 76%
    repeats = min(REPEATS_MAX, round(3 * math.log2(occurrences))) if occurrences > 1 else 0
    overlooked = _overlooked(locations)
    value = min(100, round(base * factor + repeats + (OVERLOOKED_BONUS if overlooked else 0)))

    factors = [f"{LEVEL_LABELS[severity]} severity: base {base}",
               f"confidence {confidence:.2f}: x {factor:.2f}"]
    if repeats:
        factors.append(f"{occurrences} occurrences in the file: +{repeats}")
    if overlooked:
        factors.append(f"found in {overlooked}, where people rarely look: +{OVERLOOKED_BONUS}")
    return Score(value, tuple(factors))


def band(score: int) -> tuple[str, str]:
    """(key, label) for a score - FR-077's default interpretation."""
    for lowest, key, label in BANDS:
        if score >= lowest:
            return key, label
    raise ValueError(score)


@dataclass(frozen=True)
class Counted:
    """One finding that counts towards its scan's score."""

    risk: int
    label: str            # e.g. "Private key in deploy.env" - for the explanation only


@dataclass(frozen=True)
class ScanScore:
    value: int | None     # None: nothing could be scored
    band: str | None
    band_label: str | None
    factors: tuple[str, ...]
    limitation: str = LIMITATION


def scan_risk(counted: Iterable[Counted], *, excluded: int = 0, not_assessed: int = 0) -> ScanScore:
    """`counted`: findings with a risk score that are not reviewed away (see NOT_COUNTED).
    Only the riskiest and those at or above SERIOUS affect the result, so a caller with
    thousands of findings may pass just those. `excluded`: reviewed away. `not_assessed`:
    found before risk was scored."""
    counted = sorted(counted, key=lambda f: -f.risk)

    notes = []
    if excluded:
        notes.append(f"{excluded} finding(s) not counted: reviewed as false positive or resolved")
    if not_assessed:
        notes.append(f"{not_assessed} finding(s) not assessed: found before PrivGuard scored risk")

    if not counted:
        if not_assessed:
            return ScanScore(None, None, None, tuple(notes))  # what remains cannot be scored - never claim 0
        key, label = band(0)
        return ScanScore(0, key, label, ("No finding counts towards the score", *notes))

    worst = counted[0]
    others = sum(f.risk >= SERIOUS for f in counted[1:])
    bonus = min(BONUS_MAX, BONUS_EACH * others)
    value = min(100, worst.risk + bonus)
    factors = [f"Riskiest finding: {worst.label} ({worst.risk})"]
    if others:
        factors.append(f"{others} other serious finding(s), risk {SERIOUS} or more: +{bonus}"
                       + (" (the most this bonus adds)" if bonus == BONUS_MAX else ""))
    key, label = band(value)
    return ScanScore(value, key, label, (*factors, *notes))
