"""Precision and recall of the detectors on the synthetic corpus (SRS 12.4).

    cd backend
    .venv/Scripts/python.exe -m tests.engine.detection_quality

Prints a per-type table, the rates SRS 12.4 asks for, then every miss and
every false alarm, so a change to a rule shows its effect in numbers. Runs
without Django.
"""

from __future__ import annotations

import statistics
import time
from collections import Counter, defaultdict

from privguard_engine.detectors import detect_segment

from .detection_corpus import CASES as FIRST_BATCH
from .detection_corpus import HARDER_CASES

CASES = FIRST_BATCH + HARDER_CASES


def evaluate(cases=CASES):
    counts: dict[str, Counter] = defaultdict(Counter)
    misses, false_alarms = [], []
    for case in cases:
        found = {(d.type, d.value) for d in detect_segment(case.text, case.location)}
        expected = set(case.expected)
        for kind, value in found & expected:
            counts[kind]["tp"] += 1
        for kind, value in found - expected:
            counts[kind]["fp"] += 1
            false_alarms.append((case, kind, value))
        for kind, value in expected - found:
            counts[kind]["gap" if case.gap else "fn"] += 1
            misses.append((case, kind, value))
    return counts, misses, false_alarms


def precision(c: Counter) -> float:
    found = c["tp"] + c["fp"]
    return c["tp"] / found if found else 1.0


def recall(c: Counter, *, with_gaps: bool) -> float:
    present = c["tp"] + c["fn"] + (c["gap"] if with_gaps else 0)
    return c["tp"] / present if present else 1.0


def seconds_per_segment(repeats: int = 5) -> float:
    """Median time to run every detector over one corpus segment (short segments: a lower bound)."""
    timings = []
    for _ in range(repeats):
        start = time.perf_counter()
        for case in CASES:
            detect_segment(case.text, case.location)
        timings.append((time.perf_counter() - start) / len(CASES))
    return statistics.median(timings)


def report() -> str:
    counts, misses, false_alarms = evaluate()
    lines = [f"{'type':<20}{'TP':>4}{'FP':>4}{'FN':>4}{'gap':>5}{'precision':>11}{'recall':>8}{'incl. gaps':>12}"]
    total = Counter()
    for kind in sorted(counts):
        c = counts[kind]
        total.update(c)
        lines.append(f"{kind:<20}{c['tp']:>4}{c['fp']:>4}{c['fn']:>4}{c['gap']:>5}"
                     f"{precision(c):>11.2f}{recall(c, with_gaps=False):>8.2f}{recall(c, with_gaps=True):>12.2f}")
    lines.append(f"{'ALL':<20}{total['tp']:>4}{total['fp']:>4}{total['fn']:>4}{total['gap']:>5}"
                 f"{precision(total):>11.2f}{recall(total, with_gaps=False):>8.2f}{recall(total, with_gaps=True):>12.2f}")
    negatives = [case for case in CASES if not case.expected]
    alarmed = {id(case) for case, _, _ in false_alarms}
    lines += [
        f"\n{len(CASES)} cases, {len(negatives)} of them look-alikes that should find nothing.",
        f"false-positive rate: {sum(id(c) in alarmed for c in negatives) / len(negatives):.2f}"
        " (share of look-alikes that produced any finding)",
        f"false-negative rate: {1 - recall(total, with_gaps=False):.2f}"
        f" ({1 - recall(total, with_gaps=True):.2f} including known gaps)",
        f"processing time:     {seconds_per_segment() * 1e6:.0f} microseconds per segment",
    ]
    for title, rows in (("Misses", misses), ("False alarms", false_alarms)):
        lines.append(f"\n{title} ({len(rows)}):")
        for case, kind, value in rows:
            marker = " [known gap]" if title == "Misses" and case.gap else ""
            lines.append(f"  {kind:<16} {value!r:<34} in {case.text!r}{marker}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
