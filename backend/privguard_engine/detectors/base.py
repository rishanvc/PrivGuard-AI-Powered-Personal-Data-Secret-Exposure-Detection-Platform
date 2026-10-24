"""Shared shapes for detectors (FR-039, SRS 8.2). Pure Python, no Django (D-002)."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

# Bump when detection rules change, so each scan records which rules searched it (FR-108).
DETECTION_VERSION = 1

# How a finding was made (FR-039). A pattern match is never presented as AI certainty.
PATTERN = "pattern"
VALIDATED = "pattern + validation"
CHECKSUM = "pattern + checksum"
CONTEXT = "context"
ENTROPY = "entropy heuristic"  # FR-054: randomness alone - the weakest evidence

PERSONAL = "personal"
SECRET = "secret"
FINANCIAL = "financial"

# type -> human label.
PERSONAL_TYPES = {
    "email_address": "Email address",
    "phone_number": "Phone number",
    "aadhaar_number": "Aadhaar number",
    "pan_number": "PAN",
    "date_of_birth": "Date of birth",
    "person_name": "Person's name",
    "postal_address": "Postal address",
    "postal_code": "PIN code",
    "employee_id": "Employee ID",
    "passport_number": "Passport number",
    "voter_id": "Voter ID (EPIC)",
    "driving_licence": "Driving licence number",
    "gender": "Gender",
    "nationality": "Nationality",
    "religion_or_caste": "Religion or caste",
    "marital_status": "Marital status",
    "blood_group": "Blood group",
}
SECRET_TYPES = {  # Cycle 6
    "private_key": "Private key",
    "cloud_credential": "Cloud credential",
    "api_token": "API key or token",
    "test_api_token": "API key (test mode or example)",
    "jwt": "JSON Web Token",
    "password": "Password",
    "secret_assignment": "Secret in configuration",
    "connection_string": "Credentials in a connection string",
    "high_entropy_secret": "Possible secret (random-looking value)",
}
FINANCIAL_TYPES = {  # Cycle 6
    "payment_card": "Payment card number",
    "test_payment_card": "Payment card (published test number)",
    "card_security_code": "Card security code (CVV)",
    "bank_account": "Bank account number",
    "ifsc_code": "IFSC code",
    "upi_id": "UPI ID",
    "gstin": "GSTIN",
    "iban": "IBAN",
    "swift_code": "SWIFT/BIC code",
    "transaction_id": "Transaction ID",
    "payment_reference": "Payment reference",
}
TYPE_LABELS = {**PERSONAL_TYPES, **SECRET_TYPES, **FINANCIAL_TYPES}
CATEGORY_OF = {
    **dict.fromkeys(PERSONAL_TYPES, PERSONAL),
    **dict.fromkeys(SECRET_TYPES, SECRET),
    **dict.fromkeys(FINANCIAL_TYPES, FINANCIAL),
}


@dataclass(frozen=True, slots=True)
class Detection:
    """One match inside one segment.

    Holds the RAW value. It exists only inside the extraction child process;
    FindingCollector turns detections into masked Findings before anything
    leaves.
    """

    type: str
    start: int
    end: int
    value: str          # the matched text, used only for masking
    key: str            # normalised value, used only to group repeats in a file
    method: str
    confidence: float   # a fixed number per rule - a ranking aid, not a probability
    explanation: str    # fixed wording; never quotes the file


@dataclass(frozen=True)
class Finding:
    """Safe to persist and display: no raw value anywhere in it."""

    category: str
    type: str
    method: str
    confidence: float
    masked_value: str
    context: str                                   # masked preview around the first occurrence
    location: Mapping[str, object]                 # first occurrence
    more_locations: tuple[Mapping[str, object], ...]
    occurrences: int
    explanation: str


@dataclass(frozen=True)
class DetectionConfig:
    # Region for phone numbers written without a country code (Cycle 5 decision: India).
    region: str = "IN"
    # Detector names to run; None runs them all.
    enabled: frozenset[str] | None = None
    # The file's type from intake ("env", "config", "code", "text"...), set per
    # file by the child. "PASSWORD=abc" is a value in a .env file, but in code
    # an unquoted right-hand side is an expression, not a secret.
    file_type: str = ""


Detector = Callable[[str, Mapping, DetectionConfig], Iterable[Detection]]
