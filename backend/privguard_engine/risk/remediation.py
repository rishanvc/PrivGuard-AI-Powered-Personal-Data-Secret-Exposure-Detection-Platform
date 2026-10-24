"""Recommended remediation for each kind of finding (FR-084). Fixed advice, never text from a file.

For secrets the first step is always to REVOKE: deleting a key from a file
does not help if the file was ever shared, emailed or committed - copies and
history keep it.
"""

from __future__ import annotations

_MOVE_OUT = "Load secrets from an environment variable or a secrets manager, never from a file."
_HISTORY = "Deleting it is not enough if the file was ever shared or committed: copies and history keep it."
_ROTATE = f"Revoke it in the system it belongs to and issue a new one. {_MOVE_OUT} {_HISTORY}"
_ACCOUNT = ("Share account details only with those who need them, and mask all but the last four digits in "
            "documents that circulate.")
_IDENTITY = "Remove or mask the number unless the document's purpose requires it, and restrict who can open the file."
_PURPOSE = "Keep it only if the document's purpose requires it."
_PUBLIC = "Public bank information: no action needed on its own. Check the account details next to it."

REMEDIATION: dict[str, str] = {
    # ---- secrets
    "private_key": ("Treat the key as compromised: create a new key pair, replace the public key wherever it is "
                    f"trusted, and delete this copy. {_HISTORY}"),
    "cloud_credential": ("Deactivate the key in the cloud provider's console now and create a new one; check the "
                         f"provider's logs for activity you do not recognise. {_MOVE_OUT} {_HISTORY}"),
    "api_token": _ROTATE,
    "connection_string": ("Change the database or service password, then build the connection string from "
                          "environment variables so the password never sits in a file."),
    "password": ("Change the password wherever it is used, then remove it from the file. Keep passwords in a "
                 "password manager or secrets manager - never in documents or code."),
    "secret_assignment": _ROTATE,
    "jwt": ("If the token may still be valid, end the session or rotate the signing key. Do not paste tokens into "
            "documents, tickets or logs."),
    "high_entropy_secret": ("Check whether this value is a secret. If it is, revoke it and issue a new one. "
                            f"{_MOVE_OUT} If it is not, mark the finding as a false positive."),
    "test_api_token": f"A test-mode or documentation key grants no real access, but good practice still applies. {_MOVE_OUT}",
    # ---- financial
    "payment_card": ("Remove the card number, or mask it to the last four digits. Card data belongs only in a "
                     "payment provider's systems (PCI DSS)."),
    "card_security_code": "Delete it. Card-industry rules (PCI DSS) forbid storing security codes at all, even encrypted.",
    "test_payment_card": "A published test number that cannot be charged: no action needed.",
    "bank_account": _ACCOUNT,
    "iban": _ACCOUNT,
    "upi_id": "Remove it if it is not needed, or limit who receives the document.",
    "transaction_id": "Usually fine to keep. Remove it before sharing publicly: it can be traced back to the payer.",
    "payment_reference": "Usually fine to keep. Remove it before sharing publicly: it can be traced back to the payer.",
    "ifsc_code": _PUBLIC,
    "swift_code": _PUBLIC,
    "gstin": ("Public business information. For a sole proprietor it contains the owner's personal PAN, so avoid "
              "publishing it next to other personal details."),
    # ---- personal
    "aadhaar_number": ("Remove it, or mask it to the last four digits as UIDAI's masked Aadhaar does. Keep full "
                       "numbers only where the law requires them, and restrict who can open the file."),
    "passport_number": _IDENTITY,
    "voter_id": _IDENTITY,
    "driving_licence": _IDENTITY,
    "religion_or_caste": ("Special-category data: keep it only for a clear lawful purpose, restrict access tightly, "
                          "or remove it."),
    "blood_group": ("Health data: keep it only where it is needed, such as an emergency-contact record, and "
                    "restrict access."),
    "pan_number": ("Mask it unless the document needs it (a tax invoice does), and limit how widely the file is "
                   "shared."),
    "phone_number": "Remove it from widely shared documents, or make sure the person agreed to share it.",
    "date_of_birth": "Remove it unless it is needed; where age matters, the year or an age range is often enough.",
    "postal_address": "Share addresses only with those who need them, and remove them from widely shared files.",
    "person_name": "Usually acceptable. Check whether the name needs to appear next to the other personal data here.",
    "email_address": ("Usually acceptable. Avoid publishing personal addresses, and use BCC when writing to many "
                      "people."),
    "gender": _PURPOSE,
    "nationality": _PURPOSE,
    "marital_status": _PURPOSE,
    "employee_id": "An internal identifier: fine inside the organisation, but remove it before sharing outside.",
    "postal_code": "Usually acceptable on its own. Check what other personal data appears with it.",
}
