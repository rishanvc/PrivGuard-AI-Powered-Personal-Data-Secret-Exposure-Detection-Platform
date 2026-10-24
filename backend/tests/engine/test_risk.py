"""Risk scoring and remediation (FR-074 to FR-077, FR-080, FR-084, SRS 8.3). Runs WITHOUT Django."""

import unittest

from privguard_engine.detectors import TYPE_LABELS
from privguard_engine.risk import (
    BANDS, LEVELS, REMEDIATION, RISK_POLICY_VERSION, Counted, band, finding_risk, scan_risk,
)
from privguard_engine.risk.scoring import BASE, BONUS_MAX, SERIOUS

PLAIN = [{"line": 1}]


class FindingRiskTests(unittest.TestCase):
    def test_worked_examples(self):
        # (severity, confidence, occurrences, locations, score); each worked by hand in D-041
        examples = [
            ("critical", 0.99, 1, PLAIN, 90),                                   # 90 x 0.996
            ("high", 0.95, 2, PLAIN, 72),                                       # 70 x 0.98 + 3
            ("low", 0.9, 1, PLAIN, 19),                                         # 20 x 0.96
            ("high", 0.95, 1, [{"part": "body", "kind": "deleted"}], 74),       # 70 x 0.98 + 5
            ("medium", 0.4, 20, PLAIN, 44),                                     # 45 x 0.76 + 10
        ]
        for severity, confidence, occurrences, locations, expected in examples:
            with self.subTest(severity=severity, occurrences=occurrences):
                self.assertEqual(finding_risk(severity, confidence, occurrences, locations).value, expected)

    def test_more_severe_or_more_certain_never_scores_lower(self):
        for confidence in (0.4, 0.75, 0.95):
            scores = [finding_risk(level, confidence, 1, PLAIN).value for level in LEVELS]
            self.assertEqual(scores, sorted(scores, reverse=True))
        for level in LEVELS:
            scores = [finding_risk(level, c, 1, PLAIN).value for c in (0.4, 0.6, 0.8, 1.0)]
            self.assertEqual(scores, sorted(scores))
            # Not merely "never lower" - a flat line passes that. Certainty must MATTER.
            self.assertLess(scores[0], scores[-1], level)

    def test_repeats_add_at_most_ten(self):
        once = finding_risk("medium", 1.0, 1, PLAIN).value
        self.assertEqual(finding_risk("medium", 1.0, 2, PLAIN).value - once, 3)
        self.assertEqual(finding_risk("medium", 1.0, 1_000_000, PLAIN).value - once, 10)

    def test_content_people_overlook_adds_five(self):
        plain = finding_risk("medium", 1.0, 1, PLAIN).value
        for location in ({"kind": "deleted"}, {"kind": "field code"}, {"sheet": "Old", "hidden": True},
                         {"part": "comments"}, {"slide": 2, "part": "notes"}, {"part": "properties"}):
            with self.subTest(location=location):
                self.assertEqual(finding_risk("medium", 1.0, 1, [PLAIN[0], location]).value - plain, 5)
        self.assertEqual(finding_risk("medium", 1.0, 1, [{"part": "body", "paragraph": 3}]).value, plain)

    def test_never_above_100(self):
        self.assertEqual(finding_risk("critical", 1.0, 1_000, [{"kind": "deleted"}]).value, 100)

    def test_factors_explain_the_score(self):
        factors = finding_risk("high", 0.95, 4, [{"hidden": True}]).factors
        self.assertEqual(factors, ("High severity: base 70", "confidence 0.95: x 0.98",
                                   "4 occurrences in the file: +6", "found in a hidden sheet, where people rarely look: +5"))


class BandTests(unittest.TestCase):
    def test_fr_077_default_interpretation(self):
        cases = {0: "low", 19: "low", 20: "moderate", 39: "moderate", 40: "high", 69: "high", 70: "critical",
                 100: "critical"}
        for score, expected in cases.items():
            with self.subTest(score=score):
                self.assertEqual(band(score)[0], expected)
        self.assertEqual([label for _, _, label in BANDS], ["Critical", "High", "Moderate", "Low"])


def counted(risk, label="A finding in a.txt"):
    return Counted(risk, label)


class ScanRiskTests(unittest.TestCase):
    def test_a_thousand_small_findings_do_not_add_up(self):
        result = scan_risk([counted(19)] * 1000)  # SRS 8.3: never a simple sum
        self.assertEqual((result.value, result.band), (19, "low"))

    def test_the_riskiest_finding_plus_three_per_other_serious_one(self):
        self.assertEqual(scan_risk([counted(80), counted(65), counted(60)]).value, 86)   # 80 + 2 x 3
        self.assertEqual(scan_risk([counted(80), counted(59), counted(59)]).value, 80)   # 59 is below SERIOUS
        self.assertEqual(scan_risk([counted(80)] + [counted(70)] * 50).value, 80 + BONUS_MAX)  # the bonus caps at 15

    def test_never_above_100(self):
        self.assertEqual(scan_risk([counted(95)] * 10).value, 100)

    def test_the_explanation_names_the_riskiest_finding(self):
        result = scan_risk([counted(90, "Private key in deploy.pem"), counted(70), counted(65)],
                           excluded=2, not_assessed=1)
        self.assertEqual(result.factors, (
            "Riskiest finding: Private key in deploy.pem (90)",
            f"2 other serious finding(s), risk {SERIOUS} or more: +6",
            "2 finding(s) not counted: reviewed as false positive or resolved",
            "1 finding(s) not assessed: found before PrivGuard scored risk",
        ))
        self.assertIn("not proof that the files are safe or unsafe", result.limitation)  # FR-080

    def test_nothing_found_scores_zero(self):
        result = scan_risk([])
        self.assertEqual((result.value, result.band), (0, "low"))

    def test_everything_reviewed_away_scores_zero(self):
        self.assertEqual(scan_risk([], excluded=3).value, 0)

    def test_nothing_scoreable_is_not_scored(self):
        result = scan_risk([], not_assessed=4)  # found before risk existed: never claim 0
        self.assertIsNone(result.value)
        self.assertIsNone(result.band)


class PolicyTests(unittest.TestCase):
    def test_every_level_has_a_base_and_every_type_has_remediation(self):
        self.assertEqual(set(BASE), set(LEVELS))
        self.assertEqual(set(REMEDIATION), set(TYPE_LABELS))
        for kind, advice in REMEDIATION.items():
            with self.subTest(kind=kind):
                self.assertTrue(advice.endswith("."))

    def test_secrets_are_revoked_not_just_deleted(self):
        for kind in ("private_key", "cloud_credential", "api_token", "secret_assignment"):
            with self.subTest(kind=kind):
                self.assertIn("history keep", REMEDIATION[kind])

    def test_version_is_recorded(self):
        self.assertIsInstance(RISK_POLICY_VERSION, int)


if __name__ == "__main__":
    unittest.main()
