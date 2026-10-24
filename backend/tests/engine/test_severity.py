"""The severity policy (FR-072, FR-073, FR-076). Runs WITHOUT Django."""

import unittest

from privguard_engine.detectors import TYPE_LABELS
from privguard_engine.risk import (
    CRITICAL, HIGH, INFORMATIONAL, LEVEL_LABELS, LEVELS, LOW, MEDIUM, POLICY, SEVERITY_POLICY_VERSION, assess,
)


class PolicyTests(unittest.TestCase):
    def test_every_kind_of_finding_has_exactly_one_level(self):
        self.assertEqual(set(POLICY), set(TYPE_LABELS))  # a new detector type must be given a level
        for kind, (level, why) in POLICY.items():
            with self.subTest(kind=kind):
                self.assertIn(level, LEVELS)
                self.assertTrue(why)

    def test_the_five_levels_of_fr_073(self):
        self.assertEqual([LEVEL_LABELS[level] for level in LEVELS],
                         ["Critical", "High", "Medium", "Low", "Informational"])
        self.assertIsInstance(SEVERITY_POLICY_VERSION, int)

    def test_levels_that_carry_a_decision(self):
        expected = {
            "private_key": CRITICAL, "api_token": CRITICAL, "connection_string": CRITICAL,
            "payment_card": HIGH, "aadhaar_number": HIGH, "password": HIGH,
            "religion_or_caste": HIGH, "blood_group": HIGH,  # special-category data
            "pan_number": MEDIUM, "phone_number": MEDIUM,
            "person_name": LOW, "ifsc_code": LOW,
            "test_payment_card": INFORMATIONAL, "test_api_token": INFORMATIONAL,
        }
        for kind, level in expected.items():
            with self.subTest(kind=kind):
                self.assertEqual(assess(kind, 0.9).level, level)


class AdjustmentTests(unittest.TestCase):
    def test_weak_evidence_lowers_the_level_by_one(self):
        self.assertEqual(assess("high_entropy_secret", 0.4).level, MEDIUM)  # usually high
        self.assertEqual(assess("email_address", 0.4).level, INFORMATIONAL)  # example.com addresses
        self.assertEqual(assess("email_address", 0.5).level, LOW)            # 0.5 is not weak

    def test_informational_cannot_go_lower(self):
        self.assertEqual(assess("test_payment_card", 0.1).level, INFORMATIONAL)

    def test_every_reason_names_its_level_and_kind(self):
        for kind in POLICY:
            for confidence in (0.95, 0.4):
                with self.subTest(kind=kind, confidence=confidence):
                    result = assess(kind, confidence)
                    self.assertTrue(result.reason.startswith(LEVEL_LABELS[result.level] + ". "))
                    self.assertIn(TYPE_LABELS[kind], result.reason)

    def test_the_reason_says_when_weak_evidence_lowered_the_level(self):
        self.assertIn("evidence is weak (confidence 0.40)", assess("password", 0.4).reason)
        self.assertNotIn("evidence is weak", assess("password", 0.9).reason)


if __name__ == "__main__":
    unittest.main()
