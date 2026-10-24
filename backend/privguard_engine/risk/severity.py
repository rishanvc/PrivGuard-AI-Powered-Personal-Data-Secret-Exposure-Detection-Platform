"""Severity: how serious one finding is (FR-056, FR-072, FR-073, FR-076).

A documented, versioned table - kind of data -> level, with the reason - and a
single adjustment: weak evidence (confidence below 0.5) lowers the level by
one. Severity answers "what should I fix first?". It is not the risk score:
Cycle 7 combines severity with occurrences, file and context into 0-100.

The worker assesses findings AFTER the child's reply has been checked, so a
child taken over by a hostile file cannot mark its own findings harmless.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..detectors import TYPE_LABELS

# Bump whenever a level or the adjustment changes: each scan records the version that assessed it.
SEVERITY_POLICY_VERSION = 1

CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL = "critical", "high", "medium", "low", "informational"
LEVELS = (CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL)  # most serious first
LEVEL_LABELS = {CRITICAL: "Critical", HIGH: "High", MEDIUM: "Medium", LOW: "Low", INFORMATIONAL: "Informational"}
WEAK_EVIDENCE = 0.5

POLICY: dict[str, tuple[str, str]] = {
    # ---- secrets: they grant access, so they come first
    "private_key": (CRITICAL, "anyone holding it can act as its owner"),
    "cloud_credential": (CRITICAL, "it can control cloud infrastructure and run up costs"),
    "api_token": (CRITICAL, "it grants access to an account or service"),
    "connection_string": (CRITICAL, "it opens a database or service directly"),
    "password": (HIGH, "it grants access wherever it is used, and passwords are often reused"),
    "secret_assignment": (HIGH, "a configured secret usually grants access to a system"),
    "jwt": (HIGH, "a valid token grants access until it expires"),
    "high_entropy_secret": (HIGH, "if it is a secret, it grants access"),
    "test_api_token": (INFORMATIONAL, "test-mode and documentation keys grant no real access"),
    # ---- financial
    "payment_card": (HIGH, "a card number enables fraud"),
    "card_security_code": (HIGH, "with the card number it enables online fraud, and must never be stored"),
    "bank_account": (HIGH, "it is the target of payment fraud and phishing"),
    "iban": (HIGH, "it identifies a bank account"),
    "upi_id": (MEDIUM, "it identifies a person's payment account"),
    "transaction_id": (LOW, "it identifies a transaction rather than a person"),
    "payment_reference": (LOW, "it identifies a payment rather than a person"),
    "ifsc_code": (LOW, "it identifies a bank branch, which is public information"),
    "swift_code": (LOW, "it identifies a bank, which is public information"),
    "gstin": (LOW, "a public business registration, though it contains the holder's PAN"),
    "test_payment_card": (INFORMATIONAL, "published test numbers cannot be charged"),
    # ---- personal
    "aadhaar_number": (HIGH, "a national identity number, used to verify identity and reach services"),
    "passport_number": (HIGH, "a travel document number, used in identity fraud"),
    "voter_id": (HIGH, "a government identity number"),
    "driving_licence": (HIGH, "a government identity number"),
    "religion_or_caste": (HIGH, "special-category data: exposure can lead to discrimination"),
    "blood_group": (HIGH, "health data, a special category under data-protection law"),
    "pan_number": (MEDIUM, "a tax identifier: widely shared on invoices, but usable for fraud"),
    "phone_number": (MEDIUM, "it reaches a person directly, and is used for account recovery"),
    "date_of_birth": (MEDIUM, "it is commonly used to verify identity"),
    "postal_address": (MEDIUM, "it locates a person"),
    "person_name": (LOW, "on its own a name reveals little, but it links other data to a person"),
    "email_address": (LOW, "it reaches a person, and attracts spam and phishing"),
    "gender": (LOW, "personal, but rarely harmful on its own"),
    "nationality": (LOW, "personal, but rarely harmful on its own"),
    "marital_status": (LOW, "personal, but rarely harmful on its own"),
    "employee_id": (LOW, "an internal identifier"),
    "postal_code": (LOW, "it narrows down where someone lives"),
}


@dataclass(frozen=True)
class Assessment:
    level: str
    reason: str  # fixed wording from this module - never text from the file


def assess(finding_type: str, confidence: float) -> Assessment:
    """The severity of one finding, with the reason in words (FR-076)."""
    level, why = POLICY[finding_type]
    reason = f"{TYPE_LABELS[finding_type]}: {why}"
    if confidence < WEAK_EVIDENCE and level != INFORMATIONAL:
        level = LEVELS[LEVELS.index(level) + 1]
        reason += f". One level lower than usual because the evidence is weak (confidence {confidence:.2f})"
    return Assessment(level, f"{LEVEL_LABELS[level]}. {reason}.")
