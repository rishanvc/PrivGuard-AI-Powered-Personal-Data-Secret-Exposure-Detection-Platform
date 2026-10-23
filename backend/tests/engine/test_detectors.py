"""Personal-data detection, masking and findings (FR-031 to FR-039, FR-085). Runs WITHOUT Django.

The corpus (detection_corpus.py) measures how well the rules work overall;
these tests pin down the individual rules and, above all, the privacy
promises: a Finding never contains a raw value, and a preview never shows a
neighbouring one.
"""

import os
import re
import shutil
import tempfile
import time
import unittest

from privguard_engine.detectors import (
    CHECKSUM, CONTEXT, PATTERN, VALIDATED, Detection, DetectionConfig, FindingCollector,
    detect_segment, verhoeff_check_digit, verhoeff_valid,
)
from privguard_engine.detectors.collector import resolve_overlaps
from privguard_engine.detectors.masking import (
    keep_ends, mask_aadhaar, mask_email, mask_name, mask_phone, mask_text, sanitise_preview,
)
from privguard_engine.extractors import ExtractionStatus, extract_file
from privguard_engine.extractors.base import Segment

from .detection_corpus import MAIL, aadhaar, wrong_checksum
from .detection_quality import CASES, evaluate, report


def found(text, location=None, **config):
    return [(d.type, d.value) for d in detect_segment(text, location or {}, DetectionConfig(**config))]


def only(text, location=None) -> Detection:
    detections = detect_segment(text, location or {})
    assert len(detections) == 1, detections
    return detections[0]


class VerhoeffTests(unittest.TestCase):
    def test_the_published_example(self):
        self.assertEqual(verhoeff_check_digit("236"), "3")
        self.assertTrue(verhoeff_valid("2363"))
        self.assertFalse(verhoeff_valid("2364"))

    def test_every_single_digit_typo_is_caught(self):
        number = "23456789012" + verhoeff_check_digit("23456789012")
        for position in range(len(number)):
            for digit in "0123456789":
                if digit != number[position]:
                    typo = number[:position] + digit + number[position + 1:]
                    with self.subTest(typo=typo):
                        self.assertFalse(verhoeff_valid(typo))

    def test_every_swap_of_neighbouring_digits_is_caught(self):
        number = "23456789012" + verhoeff_check_digit("23456789012")
        for i in range(len(number) - 1):
            swapped = number[:i] + number[i + 1] + number[i] + number[i + 2:]
            with self.subTest(swapped=swapped):
                self.assertFalse(verhoeff_valid(swapped))


class MaskingTests(unittest.TestCase):
    def test_each_mask(self):
        self.assertEqual(mask_email(f"priya.sharma@{MAIL}"), f"p***@{MAIL}")
        self.assertEqual(mask_phone("+44 20 7946 0001", "44"), "+44 ** **** **01")
        self.assertEqual(mask_phone("98765 43210", "91"), "***** ***10")  # no "+": no country code to keep
        self.assertEqual(mask_aadhaar("234567890123"), "XXXX XXXX 0123")
        self.assertEqual(mask_name("Ana Example"), "A** E******")
        self.assertEqual(keep_ends("ABCPE1234F", end=4), "******234F")

    def test_long_text_is_cut(self):
        masked = mask_text("x" * 40, keep=1, limit=32)
        self.assertEqual(len(masked), 32)
        self.assertTrue(masked.endswith("…"))

    def test_previews_lose_every_run_of_four_or_more_digits(self):
        self.assertEqual(sanitise_preview("Room 101, ref 4421, card 41111111"), "Room 101, ref ****, card ********")


class RuleTests(unittest.TestCase):
    """Each rule's confidence and method: fixed numbers, so a change shows up here."""

    def test_emails(self):
        self.assertEqual(only("Write to ana@example.com").confidence, 0.4)          # reserved for documentation
        self.assertEqual(only(f"Escalations go to support@{MAIL}").confidence, 0.5)  # a shared role mailbox
        self.assertEqual(only(f"Contact rahul.verma@{MAIL}").confidence, 0.9)
        labelled = only(f"Email: rahul.verma@{MAIL}")
        self.assertEqual((labelled.confidence, labelled.method), (0.95, PATTERN))

    def test_phones(self):
        self.assertEqual(found("Invoice 9876543210 paid in full"), [])  # bare digits, no label
        labelled = only("Ph: 9876543210")
        self.assertEqual((labelled.confidence, labelled.method, labelled.key), (0.95, VALIDATED, "+919876543210"))
        self.assertEqual(only("Call +91 98765 43210 today").confidence, 0.8)
        # Written differently, still the same number: the same key groups them.
        self.assertEqual(only("Mobile: +91-98765-43210").key, only("Mobile: 98765 43210").key)

    def test_aadhaar(self):
        good = aadhaar("23456789012")
        labelled = only(f"Aadhaar: {good}")
        self.assertEqual((labelled.confidence, labelled.method), (0.95, CHECKSUM))
        self.assertEqual(only(f"Identity verified with {good} on file").confidence, 0.8)  # grouping alone
        self.assertEqual(found(f"Order reference {aadhaar('56789012345', '')}"), [])     # bare and unlabelled
        self.assertEqual(found(f"Aadhaar: {wrong_checksum('23456789012')}"), [])
        self.assertEqual(found("Card 4111 1111 1111 1111"), [])                          # not inside a longer number

    def test_pan(self):
        labelled = only("PAN: ABCPE1234F")
        self.assertEqual((labelled.confidence, labelled.method), (0.95, PATTERN))
        self.assertIn("an individual", labelled.explanation)  # 4th letter P
        self.assertEqual(only("Invoice ABCPE1234F attached").confidence, 0.75)
        self.assertEqual(found("Product code ABCDE1234F"), [])  # D is not a holder type

    def test_dates_need_a_birth_label(self):
        self.assertEqual(found("Meeting moved to 17/05/1990"), [])
        self.assertEqual(only("DOB: 17/05/1990").method, CONTEXT)
        self.assertEqual(found("DOB: 17/05/2090"), [])  # in the future

    def test_a_name_stops_where_the_next_field_starts(self):
        self.assertEqual(found("Customer Name: Neha Gupta Order ID: 4421"), [("person_name", "Neha Gupta")])
        self.assertEqual(found("Approved by Mr. Arjun Mehta Ref 4521"), [("person_name", "Arjun Mehta")])
        self.assertEqual(found("Name: Ana Example Date: 17/05/2026"), [("person_name", "Ana Example")])

    def test_config_chooses_the_detectors(self):
        text = f"Email: ana@{MAIL}, PAN: ABCPE1234F"
        self.assertEqual(found(text, enabled=frozenset({"email"})), [("email_address", f"ana@{MAIL}")])
        self.assertEqual(found(text, enabled=frozenset()), [])


def detection(start, end, confidence, type_="t"):
    return Detection(type_, start, end, "x", "x", PATTERN, confidence, "")


class OverlapTests(unittest.TestCase):
    def test_the_more_confident_detection_wins(self):
        kept = resolve_overlaps([detection(0, 10, 0.8, "a"), detection(5, 12, 0.9, "b")])
        self.assertEqual([d.type for d in kept], ["b"])

    def test_on_a_tie_the_longer_span_wins(self):
        kept = resolve_overlaps([detection(2, 5, 0.8, "short"), detection(0, 10, 0.8, "long")])
        self.assertEqual([d.type for d in kept], ["long"])

    def test_neighbours_that_only_touch_are_both_kept_in_text_order(self):
        kept = resolve_overlaps([detection(5, 10, 0.9, "second"), detection(0, 5, 0.5, "first")])
        self.assertEqual([d.type for d in kept], ["first", "second"])

    def test_a_chain_of_overlaps_is_resolved_by_confidence_not_order(self):
        # b overlaps a and c; a and c don't overlap each other. b is most confident.
        kept = resolve_overlaps([detection(0, 6, 0.8, "a"), detection(4, 12, 0.9, "b"), detection(10, 16, 0.8, "c")])
        self.assertEqual([d.type for d in kept], ["b"])

    def test_cost_grows_linearly_with_the_number_of_detections(self):
        # One hostile line can hold ~166,000 matches. Comparing every pair
        # (the first version) took ~2.4 s for 10,000 and would take minutes here.
        many = [detection(i * 10, i * 10 + 5, 0.5) for i in range(200_000)]
        started = time.perf_counter()
        self.assertEqual(len(resolve_overlaps(many)), 200_000)
        self.assertLess(time.perf_counter() - started, 5)


def text_of(finding) -> str:
    """Everything a Finding would put in the database or on screen."""
    return " | ".join(map(str, (finding.masked_value, finding.context, finding.explanation,
                                finding.location, finding.more_locations)))


def collect(*segments, **options):
    collector = FindingCollector(**options)
    for text, location in segments:
        collector(Segment(text, location))
    return collector


class CollectorTests(unittest.TestCase):
    def test_a_preview_never_shows_a_neighbouring_value(self):
        findings = collect(("Name: Rahul Verma, Mobile: 98765 43210, DOB: 17/05/1990", {"line": 1})).findings()
        self.assertEqual(len(findings), 3)
        for finding in findings:
            for raw in ("Rahul", "Verma", "98765", "43210", "17/05/1990"):
                self.assertNotIn(raw, finding.context)
        name = next(f for f in findings if f.type == "person_name")
        self.assertEqual(name.context, "Name: R**** V****, Mobile: ***** ***10, DOB: **/**/****")

    def test_numbers_no_detector_claimed_are_masked_in_previews(self):
        finding, = collect(("Name: Rahul Verma, account 12345678", {"line": 1})).findings()
        self.assertNotIn("12345678", finding.context)
        self.assertIn("account ********", finding.context)

    def test_categorical_values_are_hidden_completely(self):
        for text in ("Gender: Female", "Blood group: B+", "Religion: Hindu"):
            with self.subTest(text=text):
                finding, = collect((text, {})).findings()
                self.assertEqual(finding.masked_value, "****")
                self.assertTrue(finding.context.endswith(": ****"))

    def test_repeats_in_a_file_become_one_finding(self):
        findings = collect(
            (f"Email: ana.example@{MAIL}", {"line": 1}),
            (f"cc ana.example@{MAIL}", {"line": 2}),
            (f"ANA.EXAMPLE@{MAIL.upper()}", {"line": 2}),  # same address, other case, same line
        ).findings()
        finding, = findings
        self.assertEqual(finding.occurrences, 3)
        self.assertEqual(finding.location, {"line": 1})
        self.assertEqual(finding.more_locations, ({"line": 2},))  # each location listed once

    def test_a_finding_shows_its_most_confident_occurrence(self):
        finding, = collect(
            ("Call +91 98765 43210 today", {"line": 1}),  # no label: 0.8
            ("Mobile: 98765 43210", {"line": 2}),         # labelled: 0.95
        ).findings()
        self.assertEqual((finding.confidence, finding.occurrences), (0.95, 2))
        self.assertEqual((finding.location, finding.more_locations), ({"line": 2}, ({"line": 1},)))
        # Explanation, preview and location all describe the SAME occurrence.
        self.assertIn("labelled 'mobile'", finding.explanation)
        self.assertEqual(finding.context, "Mobile: ***** ***10")

    def test_the_header_is_never_stored_in_a_location(self):
        # A CSV with no header row: its "header" is really the first row of DATA.
        finding, = collect((f"rahul.verma@{MAIL}", {"row": 2, "column": 2, "line": 2, "header": "Rahul Verma"})).findings()
        self.assertEqual(finding.location, {"row": 2, "column": 2, "line": 2})
        self.assertNotIn("rahul verma", text_of(finding).casefold())

    def test_locations_are_capped(self):
        collector = collect(*[(f"Email: ana@{MAIL}", {"line": n}) for n in range(1, 6)], max_locations=3)
        finding, = collector.findings()
        self.assertEqual(finding.occurrences, 5)
        self.assertEqual(1 + len(finding.more_locations), 3)

    def test_too_many_findings_are_reported_as_truncated(self):
        collector = collect(*[(f"Email: person{n}@{MAIL}", {"line": n}) for n in range(3)], max_findings=2)
        self.assertEqual(len(collector.findings()), 2)
        self.assertEqual(collector.stats(), {"detections": 3, "findings": 2,
                                             "by_type": {"email_address": 2}, "truncated": True})

    def test_no_finding_from_the_corpus_contains_a_raw_value(self):
        checked = 0
        for case in CASES:
            findings = collect((case.text, case.location)).findings()
            shown = " || ".join(map(text_of, findings)).casefold()
            for _, value in case.expected:
                # Known gaps are excluded: a value no rule detects is not masked, and can
                # appear in a NEIGHBOUR's preview - a documented limit (decisions.md).
                # One-letter values ("M") would match any text; their mask is tested above.
                if case.gap or len(value) < 2:
                    continue
                with self.subTest(text=case.text, value=value):
                    self.assertNotIn(value.casefold(), shown)
                    checked += 1
            for finding in findings:
                self.assertIsNone(re.search(r"\d{5,}", finding.masked_value + finding.context), finding)
        self.assertGreater(checked, 60)  # the loop really ran over the corpus


class SinkTests(unittest.TestCase):
    def test_the_collector_is_an_extraction_sink(self):
        folder = tempfile.mkdtemp(prefix="privguard-detect-")
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "stored")  # no extension, like a real upload
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write("Name,Mobile,Email,Notes\r\n"
                         f"Ana Example,98765 43210,ana.example@{MAIL},Order 4421\r\n"
                         f"Rahul Verma,+91 98765 43211,rahul.verma@{MAIL},\r\n")

        collector = FindingCollector()
        result = extract_file(path, "csv", sink=collector)

        self.assertEqual(result.status, ExtractionStatus.SUCCEEDED)
        self.assertEqual(collector.stats()["by_type"], {"person_name": 2, "phone_number": 2, "email_address": 2})
        names = sorted(f.masked_value for f in collector.findings() if f.type == "person_name")
        self.assertEqual(names, ["A** E******", "R**** V****"])
        everything = " ".join(map(text_of, collector.findings()))
        for raw in ("Ana Example", "Rahul Verma", "98765 43210", "ana.example@"):
            self.assertNotIn(raw, everything)
        for finding in collector.findings():
            self.assertNotIn("header", finding.location)


class QualityGateTests(unittest.TestCase):
    def test_the_corpus_has_no_false_alarms_and_no_unexpected_misses(self):
        counts, misses, false_alarms = evaluate()
        unexpected = [m for m in misses if not m[0].gap]
        self.assertEqual((unexpected, false_alarms), ([], []), "\n" + report())


if __name__ == "__main__":
    unittest.main()
