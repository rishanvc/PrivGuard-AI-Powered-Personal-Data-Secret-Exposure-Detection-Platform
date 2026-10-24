"""Financial information (FR-040 to FR-045). Runs WITHOUT Django.

Synthetic numbers are built at runtime with real check digits (secret_fixtures.py).
The literal numbers here are published examples: card networks' test cards,
the IBAN registry's example, and the GST documentation's sample GSTIN.
"""

import unittest

from privguard_engine.detectors import (
    CHECKSUM, CONTEXT, PATTERN, DetectionConfig, FindingCollector, detect_segment, gstin_check_character, iban_valid,
    luhn_check_digit, luhn_valid,
)
from privguard_engine.detectors.financial import TEST_CARDS, card_network
from privguard_engine.extractors.base import Segment

from . import secret_fixtures as s


def detections(text, **location):
    return detect_segment(text, location, DetectionConfig(file_type="text"))


def found(text, **location):
    return [(d.type, d.value) for d in detections(text, **location)]


def only(text, **location):
    result = detections(text, **location)
    assert len(result) == 1, result
    return result[0]


def masked(text, **location):
    collector = FindingCollector(DetectionConfig(file_type="text"))
    collector(Segment(text, location))
    result, = collector.findings()
    return result


class ChecksumTests(unittest.TestCase):
    """Each algorithm reproduces a published example - then catches every single-character typo."""

    def test_luhn_on_published_test_cards(self):
        for number in sorted(TEST_CARDS):
            with self.subTest(number=number):
                self.assertTrue(luhn_valid(number))
                self.assertIsNotNone(card_network(number))

    def test_luhn_catches_every_single_digit_typo(self):
        number = s.card_number("4")
        self.assertEqual(luhn_check_digit(number[:-1]), number[-1])
        for i in range(len(number)):
            for digit in "0123456789":
                if digit != number[i]:
                    with self.subTest(position=i, digit=digit):
                        self.assertFalse(luhn_valid(number[:i] + digit + number[i + 1:]))

    def test_iban_registry_example_and_typos(self):
        example = "GB82WEST12345698765432"  # the example in the SWIFT IBAN registry
        self.assertTrue(iban_valid(example))
        for i in range(4, len(example)):
            replacement = "0" if example[i] != "0" else "1"
            with self.subTest(position=i):
                self.assertFalse(iban_valid(example[:i] + replacement + example[i + 1:]))

    def test_gstin_documentation_sample(self):
        self.assertEqual(gstin_check_character("27AAPFU0939F1Z"), "V")  # GST portal's sample: 27AAPFU0939F1ZV


class CardTests(unittest.TestCase):
    def test_networks_by_prefix_and_length(self):
        examples = {"4111111111111111": "Visa", "5105105105105100": "Mastercard", "378282246310005": "American Express",
                    "6011111111111117": "Discover", "3530111333300000": "JCB", s.card_number("6080"): "RuPay",
                    s.card_number("62"): "UnionPay", s.card_number("1"): None,
                    s.card_number("37", 16): None}  # Amex numbers are 15 digits, never 16
        for number, network in examples.items():
            with self.subTest(number=number):
                self.assertEqual(card_network(number), network)

    def test_confidence_comes_from_context(self):
        number = s.card_number("4")
        self.assertEqual(found(f"Order {number} shipped"), [])  # bare: 1 in 10 order numbers pass Luhn
        grouped = only(f"Ref {s.grouped(number)}")
        self.assertEqual((grouped.type, grouped.method, grouped.confidence), ("payment_card", CHECKSUM, 0.85))
        self.assertEqual(only(f"Debit card: {number}").confidence, 0.95)
        self.assertEqual(only(number, header="Card Number").confidence, 0.95)

    def test_published_test_cards_are_marked_as_such(self):
        self.assertEqual(only("4242424242424242").type, "test_payment_card")  # even bare: it is recognised exactly


class BankTests(unittest.TestCase):
    def test_an_iban_followed_by_capitals_is_cut_at_its_country_length(self):
        iban = s.grouped(s.iban("GB", 22))
        self.assertEqual(found(f"Pay into {iban} BIC CODE ON FILE"), [("iban", iban)])

    def test_ifsc_needs_a_label_or_a_known_bank(self):
        self.assertEqual(only("IFSC: HDFC0001234").confidence, 0.95)          # label and known bank
        self.assertEqual(only("Branch HDFC0001234").confidence, 0.85)         # known bank alone
        self.assertEqual(only("IFSC: ZZZZ0001234").confidence, 0.85)          # label alone
        self.assertEqual(found("Part ZZZZ0001234 in stock"), [])              # neither: a product code

    def test_upi_ids_and_their_look_alikes(self):
        known = only("Pay to asha.example@okaxis")
        self.assertEqual((known.type, known.method, known.confidence), ("upi_id", PATTERN, 0.9))
        labelled = only("UPI: ravi.example@newpsp")
        self.assertEqual((labelled.method, labelled.confidence), (CONTEXT, 0.75))
        self.assertEqual(found("Mail noreply@icici.co.in")[0][0], "email_address")  # a domain: an email address
        self.assertEqual(found("Server user@localhost refused"), [])

    def test_labels_need_a_colon_unless_they_are_distinctive(self):
        self.assertEqual(found("UTR 430112345678"), [("transaction_id", "430112345678")])
        self.assertEqual(found("SWIFT TRANSFER COMPLETED"), [])
        self.assertEqual(found("Account: 50100123456789"), [("bank_account", "50100123456789")])
        self.assertEqual(found("Account name: Synthetic Traders"), [])

    def test_columns_supply_the_label(self):
        self.assertEqual(found("123", header="CVV"), [("card_security_code", "123")])
        self.assertEqual(found("50100123456789", header="A/C No"), [("bank_account", "50100123456789")])

    def test_an_invalid_gstin_is_not_reported(self):
        gstin = s.gstin("29")
        self.assertEqual(found(f"GSTIN: {gstin}"), [("gstin", gstin)])
        self.assertEqual(found(f"GSTIN: {s.wrong_last_character(gstin)}"), [])


class MaskingTests(unittest.TestCase):
    def test_financial_masks(self):
        card = s.card_number("4")
        iban = s.iban("DE", 22)
        cases = {
            f"Card no: {s.grouped(card)}": f"**** **** **** {card[-4:]}",
            "CVV: 123": "***",
            f"IBAN: {iban}": "DE" + "*" * 16 + iban[-4:],
            "IFSC: HDFC0001234": "HDFC*******",
            "SWIFT: HDFCINBB": "HDFC****",
            "Pay to asha.example@okaxis": "a***@okaxis",
            f"GSTIN: {s.gstin('29')}": "29" + "*" * 13,
            "UTR: 430112345678": "********5678",
        }
        for text, expected in cases.items():
            with self.subTest(expected=expected):
                result = masked(text)
                self.assertEqual(result.masked_value, expected)
                self.assertEqual(result.category, "financial")


if __name__ == "__main__":
    unittest.main()
