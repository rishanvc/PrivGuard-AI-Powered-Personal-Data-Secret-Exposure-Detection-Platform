"""Financial information (FR-040 to FR-045). Cycle 6 scope: India, payment cards and IBAN.

Checksums do most of the work, and each was verified against a published example:
  payment card  Luhn - 1 in 10 random numbers pass, so a card also needs a
                card network's prefix and length, and either the usual
                grouping or a label (like Aadhaar, D-030);
  IBAN          mod-97 - 1 in 97 pass, plus each country's fixed length;
  GSTIN         Luhn mod 36 over digits and letters - 1 in 36 pass.
IFSC, SWIFT/BIC, bank accounts, security codes and payment references have no
checksum: they need a label or a column header (FR-044).
"""

from __future__ import annotations

import re

from .base import CHECKSUM, CONTEXT, PATTERN, Detection, DetectionConfig
from .context import header_is, header_mentions, label_before, label_regex, normalise

ALPHANUMERIC = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# ------------------------------------------------------------------ payment cards (FR-040)


def luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def luhn_check_digit(digits: str) -> str:
    """The digit to append so the result passes Luhn (used to build test data)."""
    return next(d for d in "0123456789" if luhn_valid(digits + d))


# (network, prefix ranges, allowed lengths). The first network that matches wins.
_NETWORKS = (
    ("Visa", ((4, 4),), (13, 16, 19)),
    ("Mastercard", ((51, 55), (2221, 2720)), (16,)),
    ("American Express", ((34, 34), (37, 37)), (15,)),
    ("Diners Club", ((300, 305), (36, 36), (38, 39)), (14, 15, 16, 17, 18, 19)),
    ("JCB", ((3528, 3589),), (16, 17, 18, 19)),
    ("Discover", ((6011, 6011), (644, 649)), (16, 17, 18, 19)),
    ("Discover or RuPay", ((65, 65),), (16, 17, 18, 19)),
    ("RuPay", ((60, 60), (81, 82), (508, 508)), (16,)),
    ("UnionPay", ((62, 62),), (16, 17, 18, 19)),
    ("Maestro", ((50, 50), (56, 58), (639, 639), (67, 67)), (13, 14, 15, 16, 17, 18, 19)),
)
# Numbers card networks and payment providers publish for testing. They pass
# every check, but cannot be charged.
TEST_CARDS = frozenset({
    "4111111111111111", "4242424242424242", "4012888888881881", "4000056655665556", "4222222222222",
    "5555555555554444", "5105105105105100", "5200828282828210", "2223003122003222",
    "378282246310005", "371449635398431", "378734493671000",
    "6011111111111117", "6011000990139424", "30569309025904", "38520000023237",
    "3530111333300000", "3566002020360505", "6200000000000005",
})
_CARD = re.compile(
    r"(?<!\d)(?<!\d[ -])(?:"
    r"\d{13,19}"                                                      # unseparated
    r"|\d{4}(?P<a>[ -])\d{4}(?P=a)\d{4}(?P=a)\d{1,4}(?:(?P=a)\d{1,3})?"  # 4-4-4-4, and 13 to 19 digits
    r"|\d{4}(?P<b>[ -])\d{6}(?P=b)\d{4,5}"                            # 4-6-5 (Amex), 4-6-4 (Diners)
    r")(?![ -]?\d)"
)
_CARD_CONTEXT = ("card", "card no", "card number", "credit card", "debit card", "cc", "cc no", "cc number", "visa",
                 "mastercard", "master card", "amex", "american express", "rupay", "maestro", "card details")


def card_network(digits: str) -> str | None:
    for network, ranges, lengths in _NETWORKS:
        if len(digits) in lengths and any(low <= int(digits[:len(str(low))]) <= high for low, high in ranges):
            return network
    return None


def detect_payment_cards(text: str, location, config: DetectionConfig):
    if sum(ch.isdigit() for ch in text) < 13:
        return
    in_card_column = header_mentions(location, _CARD_CONTEXT)
    for match in _CARD.finditer(text):
        digits = re.sub(r"\D", "", match.group())
        network = card_network(digits)
        if network is None or not luhn_valid(digits):
            continue
        if digits in TEST_CARDS:
            yield Detection("test_payment_card", match.start(), match.end(), match.group(), digits, CHECKSUM, 0.9,
                            f"A {network} number published for payment testing: it passes every check but "
                            "cannot be charged.")
            continue
        context = in_card_column or label_before(text, match.start(), _CARD_CONTEXT)
        grouped = not match.group().isdigit()
        if not (grouped or context):
            continue  # bare and unlabelled: 1 in 10 order numbers would pass Luhn too
        reasons = [f"Passes the Luhn checksum and has the prefix and length of a {network} card"]
        reasons.append(f"labelled '{context}'" if context else "written in the usual groups of digits")
        yield Detection("payment_card", match.start(), match.end(), match.group(), digits, CHECKSUM,
                        0.95 if context else 0.85, "; ".join(reasons) + ".")


# ------------------------------------------------------------------ IBAN (FR-041)

# Lengths from the SWIFT IBAN registry. An unknown country is never accepted.
IBAN_LENGTHS = {
    "AD": 24, "AE": 23, "AL": 28, "AT": 20, "AZ": 28, "BA": 20, "BE": 16, "BG": 22, "BH": 22, "BR": 29, "BY": 28,
    "CH": 21, "CR": 22, "CY": 28, "CZ": 24, "DE": 22, "DK": 18, "DO": 28, "EE": 20, "EG": 29, "ES": 24, "FI": 18,
    "FO": 18, "FR": 27, "GB": 22, "GE": 22, "GI": 23, "GL": 18, "GR": 27, "GT": 28, "HR": 21, "HU": 28, "IE": 22,
    "IL": 23, "IQ": 23, "IS": 26, "IT": 27, "JO": 30, "KW": 30, "KZ": 20, "LB": 28, "LC": 32, "LI": 21, "LT": 20,
    "LU": 20, "LV": 21, "MC": 27, "MD": 24, "ME": 22, "MK": 19, "MR": 27, "MT": 31, "MU": 30, "NL": 18, "NO": 15,
    "PK": 24, "PL": 28, "PS": 29, "PT": 25, "QA": 29, "RO": 24, "RS": 22, "SA": 24, "SC": 31, "SE": 24, "SI": 19,
    "SK": 24, "SM": 27, "ST": 25, "SV": 28, "TL": 23, "TN": 24, "TR": 26, "UA": 29, "VA": 22, "VG": 24, "XK": 20,
}
_IBAN = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}")


def iban_valid(compact: str) -> bool:
    """mod-97 (ISO 13616): move the first four characters to the end, read A as 10 ... Z as 35."""
    rearranged = compact[4:] + compact[:4]
    return int("".join(str(ALPHANUMERIC.index(ch)) for ch in rearranged)) % 97 == 1


def detect_ibans(text: str, location, config: DetectionConfig):
    for match in _IBAN.finditer(text):
        country = match.group()[:2]
        length = IBAN_LENGTHS.get(country)
        if length is None:
            continue
        # The pattern is greedy ("... 7654 32 BIC CODE" runs on into the next word),
        # so cut the candidate at its country's length - counting characters, not spaces.
        seen, end = 0, match.start()
        for end in range(match.start(), match.end()):
            if text[end] != " ":
                seen += 1
                if seen == length:
                    break
        if seen < length or (end + 1 < len(text) and text[end + 1].isalnum()):
            continue
        value = text[match.start():end + 1]
        compact = value.replace(" ", "")
        if iban_valid(compact):
            yield Detection("iban", match.start(), end + 1, value, compact, CHECKSUM, 0.95,
                            f"An IBAN for {country}: the right length for that country, and its check digits "
                            "pass the mod-97 test.")


# ------------------------------------------------------------------ GSTIN (FR-042)

_GSTIN = re.compile(r"(?<![A-Za-z0-9])(\d{2})([A-Z]{5}\d{4}[A-Z])[1-9A-Z]Z[0-9A-Z](?![A-Za-z0-9])")
_GST_STATES = frozenset(f"{n:02d}" for n in (*range(1, 39), 97, 99))


def gstin_check_character(first_fourteen: str) -> str:
    """Luhn mod 36: alternate weights 1 and 2 from the left; each product counts as its quotient plus remainder."""
    total = 0
    for i, ch in enumerate(first_fourteen):
        product = ALPHANUMERIC.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return ALPHANUMERIC[(36 - total % 36) % 36]


def detect_gstins(text: str, location, config: DetectionConfig):
    for match in _GSTIN.finditer(text):
        value = match.group()
        if match.group(1) in _GST_STATES and gstin_check_character(value[:14]) == value[14]:
            yield Detection("gstin", match.start(), match.end(), value, value, CHECKSUM, 0.95,
                            "A GST registration number with a valid check character. Its middle ten characters "
                            "are the holder's PAN - for a sole proprietor, a person's PAN.")


# ------------------------------------------------------------------ IFSC (FR-042)

_IFSC = re.compile(r"(?<![A-Za-z0-9])([A-Z]{4})0[A-Z0-9]{6}(?![A-Za-z0-9])")
_IFSC_CONTEXT = ("ifsc", "ifsc code", "ifs code", "branch code", "neft", "rtgs", "imps", "bank code")
# The first four letters are the bank's own code. These are some of India's largest banks.
_INDIAN_BANKS = frozenset({
    "SBIN", "HDFC", "ICIC", "UTIB", "PUNB", "BARB", "CNRB", "UBIN", "BKID", "IOBA", "IDIB", "KKBK", "YESB", "INDB",
    "IDFB", "FDRL", "CBIN", "MAHB", "UCBA", "PSIB", "KARB", "SIBL", "CIUB", "TMBL", "KVBL", "RATN", "AUBL", "JAKA",
    "HSBC", "SCBL", "CITI", "DBSS", "DEUT", "PYTM", "AIRP",
})


def detect_ifsc(text: str, location, config: DetectionConfig):
    for match in _IFSC.finditer(text):
        context = header_mentions(location, _IFSC_CONTEXT) or label_before(text, match.start(), _IFSC_CONTEXT, window=30)
        known_bank = match.group(1) in _INDIAN_BANKS
        if not (context or known_bank):
            continue  # 4 letters, a zero and 6 characters is also a product code
        reasons = ["The format of an Indian bank branch code (IFSC)"]
        if known_bank:
            reasons.append("its first four letters are a known bank's code")
        if context:
            reasons.append(f"labelled '{context}'")
        yield Detection("ifsc_code", match.start(), match.end(), match.group(), match.group(), CONTEXT,
                        0.95 if context and known_bank else 0.85, "; ".join(reasons) + ".")


# ------------------------------------------------------------------ UPI IDs

_UPI = re.compile(
    r"(?<![\w.+-])(?P<user>[A-Za-z0-9][A-Za-z0-9._-]{1,255})@(?P<handle>[A-Za-z][A-Za-z0-9]{1,63})"
    r"(?![\w@-])(?!\.[A-Za-z])"  # "...@okaxis.com" would be an email address
)
_UPI_HANDLES = frozenset({
    "upi", "ybl", "ibl", "axl", "okaxis", "okhdfcbank", "okicici", "oksbi", "paytm", "ptyes", "ptaxis", "pthdfc",
    "ptsbi", "apl", "yapl", "rapl", "abfspay", "axisb", "axisbank", "icici", "hdfcbank", "sbi", "kotak", "kbl",
    "federal", "fbl", "indus", "rbl", "idfcbank", "idfcfirst", "aubank", "jupiteraxis", "freecharge", "ikwik",
    "airtel", "jio", "slice", "naviaxis", "waaxis", "wahdfcbank", "wasbi", "waicici", "pnb", "barodampay", "boi",
    "cnrb", "mahb", "yesbank", "yesbankltd", "postbank", "dbs", "hsbc", "citi", "sc",
})
_UPI_CONTEXT = ("upi", "upi id", "vpa", "upi address", "pay to", "gpay", "google pay", "phonepe", "paytm", "bhim")


def detect_upi_ids(text: str, location, config: DetectionConfig):
    if "@" not in text:
        return
    for match in _UPI.finditer(text):
        handle = match.group("handle").lower()
        if handle in _UPI_HANDLES:
            yield Detection("upi_id", match.start(), match.end(), match.group(), match.group().lower(), PATTERN, 0.9,
                            "A UPI ID: '@' followed by a known payment app's handle.")
            continue
        context = header_mentions(location, _UPI_CONTEXT) or label_before(text, match.start(), _UPI_CONTEXT, window=30)
        if context:
            yield Detection("upi_id", match.start(), match.end(), match.group(), match.group().lower(), CONTEXT, 0.75,
                            f"Shaped like a UPI ID and labelled '{context}'.")


# ------------------------------------------------------------------ labelled fields (FR-041, FR-042, FR-043)

# field -> (label phrases, value pattern, needs a digit, confidence, explanation, a plain space may follow the label)
_LABELLED = {
    "bank_account": (
        # A bare "Account" is safe here: its value must also be 9 to 18 digits, which a name never is.
        ("account", "a/c", "account number", "account no", "account num", "acct no", "acct number", "acc no",
         "a/c no", "a/c number", "ac no", "bank account", "bank account number", "bank account no",
         "beneficiary account", "beneficiary account number", "savings account", "current account"),
        r"\d(?:[ -]?\d){8,17}(?![ -]?\d)", True, 0.85, "A bank account number (9 to 18 digits)", False),
    "swift_code": (
        # Never space-separated: in "SWIFT TRANSFER", TRANSFER has the shape of a bank code.
        ("swift", "swift code", "bic", "bic code", "swift bic", "swift/bic", "bic/swift"),
        r"[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?(?![A-Za-z0-9])", False, 0.85, "A SWIFT/BIC bank code", False),
    "card_security_code": (
        ("cvv", "cvv2", "cvc", "cvc2", "security code", "card security code", "card verification code",
         "card verification value"),
        r"\d{3,4}(?!\d)", True, 0.85,
        "A card security code. Card-industry rules (PCI DSS) forbid storing it at all", False),
    "transaction_id": (
        # Bank text messages write "UTR 4301..." and "Txn ID T26..." with no colon.
        ("transaction id", "transaction no", "transaction number", "transaction ref", "transaction reference",
         "txn id", "txn no", "txn ref", "utr", "utr no", "utr number", "rrn", "upi ref", "upi ref no",
         "upi transaction id"),
        r"[A-Za-z0-9][A-Za-z0-9/_-]{4,38}[A-Za-z0-9](?![A-Za-z0-9])", True, 0.75, "A transaction identifier", True),
    "payment_reference": (
        ("payment reference", "payment ref", "payment id", "payment ref no"),
        r"[A-Za-z0-9][A-Za-z0-9/_-]{4,38}[A-Za-z0-9](?![A-Za-z0-9])", True, 0.75, "A payment reference", True),
}
_LABEL_PATTERNS = {field: label_regex(spec[0], space_separated=spec[5]) for field, spec in _LABELLED.items()}
_VALUE_PATTERNS = {field: re.compile(spec[1]) for field, spec in _LABELLED.items()}
_HEADERS = {field: {normalise(p) for p in spec[0]} for field, spec in _LABELLED.items()}


def detect_labelled_financial(text: str, location, config: DetectionConfig):
    for field, (phrases, _, needs_digit, confidence, what, _) in _LABELLED.items():
        column = header_is(location, _HEADERS[field])
        if column:
            value = text.strip()
            if _VALUE_PATTERNS[field].fullmatch(value):
                start = text.index(value)
                yield Detection(field, start, start + len(value), value, value.casefold(), CONTEXT, confidence,
                                f"{what}, in a column headed '{column}'.")
            continue
        for label in _LABEL_PATTERNS[field].finditer(text):
            found = _VALUE_PATTERNS[field].match(text, label.end())
            if not found or (needs_digit and not any(ch.isdigit() for ch in found.group())):
                continue
            yield Detection(field, found.start(), found.end(), found.group(), found.group().casefold(), CONTEXT,
                            confidence, f"{what}, following the label '{normalise(label.group('label'))}'.")
