"""Credential-shaped strings for tests, assembled at runtime.

None of these is a real credential. Each is built from fragments, so this
repository never contains a literal in a real credential's format: PrivGuard's
own rule (no secrets in source code), GitHub's push protection, and other
people's secret scanners all stay quiet. A fixed seed makes the "random" parts
identical on every run, so test results are repeatable.
"""

import base64
import json
import random
import string

_rng = random.Random(20261024)

ALNUM = string.ascii_letters + string.digits
BASE32 = string.ascii_uppercase + "234567"
HEX = "0123456789abcdef"
URLSAFE = ALNUM + "-_"
B64 = ALNUM + "+/"


def rand(length: int, alphabet: str = ALNUM) -> str:
    return "".join(_rng.choice(alphabet) for _ in range(length))


def join(*fragments: str) -> str:
    return "".join(fragments)


def mixed(length: int) -> str:
    """Random, and guaranteed to contain an upper-case letter, a lower-case letter and a digit."""
    return join(rand(length - 3), "Q", "q", "7")


def b64url(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


# ---- known formats
def aws_key_id() -> str:
    return join("AK", "IA", rand(16, BASE32))


def aws_documentation_key_id() -> str:
    return join("AK", "IA", "IOSFODNN7", "EXAM", "PLE")  # the example AWS publishes in its own docs


def aws_secret_key() -> str:
    return rand(40, ALNUM + "/+")


def github_token() -> str:
    return join("gh", "p_", rand(36))


def gitlab_token() -> str:
    return join("gl", "pat-", rand(20, URLSAFE))


def slack_bot_token() -> str:
    return join("xo", "xb-", rand(11, string.digits), "-", rand(13, string.digits), "-", rand(24))


def stripe_live_key() -> str:
    return join("sk", "_li", "ve_", rand(24))


def stripe_test_key() -> str:
    return join("sk", "_te", "st_", rand(24))


def google_api_key() -> str:
    return join("AI", "za", rand(35, URLSAFE))


def openai_key() -> str:
    return join("sk-", "proj-", rand(24, URLSAFE), "T3Blbk", "FJ", rand(24, URLSAFE))


def huggingface_token() -> str:
    return join("h", "f_", rand(34, string.ascii_letters))


def sendgrid_key() -> str:
    return join("S", "G.", rand(22, URLSAFE), ".", rand(43, URLSAFE))


def telegram_bot_token() -> str:
    return join(rand(9, string.digits), ":A", "A", rand(33, URLSAFE))


def azure_account_key() -> str:
    return join(rand(86, B64), "==")


# ---- structures
def jwt(payload: dict | None = None) -> str:
    claims = payload or {"sub": "synthetic-user-42", "exp": 1893456000}
    return join(b64url({"alg": "HS256", "typ": "JWT"}), ".", b64url(claims), ".", rand(43, URLSAFE))


def pem_begin(kind: str = "RSA PRIVATE KEY") -> str:
    return join("-----BEG", "IN ", kind, "-----")


def pem_end(kind: str = "RSA PRIVATE KEY") -> str:
    return join("-----EN", "D ", kind, "-----")


def pem_body() -> str:
    return rand(64, B64)


def password() -> str:
    """Letters, a symbol and digits - shaped like a human-chosen password."""
    return join(rand(6, string.ascii_letters), "@", rand(3, string.digits))


# ---- financial (Cycle 6): synthetic numbers with REAL check digits, so they exercise the real checks
def card_number(prefix: str = "4", length: int = 16) -> str:
    from privguard_engine.detectors import luhn_check_digit

    body = prefix + rand(length - len(prefix) - 1, string.digits)
    return body + luhn_check_digit(body)


def grouped(digits: str) -> str:
    return " ".join(digits[i:i + 4] for i in range(0, len(digits), 4))


def iban(country: str = "DE", length: int = 22) -> str:
    """A synthetic IBAN: random account part, check digits computed by ISO 13616 mod-97."""
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    bban = rand(length - 4, string.digits)
    remainder = int("".join(str(alphabet.index(ch)) for ch in bban + country + "00")) % 97
    return f"{country}{98 - remainder:02d}{bban}"


def gstin(state: str = "29", pan: str = "ABCPE1234F") -> str:
    from privguard_engine.detectors import gstin_check_character

    first = f"{state}{pan}1Z"
    return first + gstin_check_character(first)


def wrong_last_character(value: str) -> str:
    return value[:-1] + ("1" if value[-1] != "1" else "2")
