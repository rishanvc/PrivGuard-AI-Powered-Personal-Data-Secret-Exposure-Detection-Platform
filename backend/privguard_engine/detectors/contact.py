"""Email addresses and phone numbers (FR-031, FR-032)."""

from __future__ import annotations

import re

import phonenumbers
from phonenumbers import Leniency, PhoneNumberFormat, PhoneNumberMatcher

from .base import PATTERN, VALIDATED, Detection, DetectionConfig
from .context import header_mentions, label_before

# ------------------------------------------------------------------ email

_EMAIL = re.compile(
    r"(?<![\w.+%-])"
    r"(?P<local>[A-Za-z0-9](?:[A-Za-z0-9._%+-]{0,62}[A-Za-z0-9_%+-])?)"
    r"@"
    r"(?P<domain>(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+(?P<tld>[A-Za-z]{2,24}))"
    r"(?![\w-])"
)
# "logo@2x.png" has the shape of an address, but ".png" is not a top-level domain anyone mails.
_FILE_EXTENSIONS = frozenset({
    "png", "jpg", "jpeg", "gif", "svg", "webp", "bmp", "ico", "css", "js", "ts", "jsx", "tsx",
    "py", "json", "xml", "html", "htm", "txt", "pdf", "zip", "map", "woff", "ttf",
})
# RFC 2606 / RFC 6761: names reserved for documentation and testing.
_RESERVED_DOMAINS = frozenset({"example.com", "example.net", "example.org"})
_RESERVED_TLDS = frozenset({"test", "example", "invalid", "localhost", "local"})
_ROLE_MAILBOXES = frozenset({
    "info", "admin", "administrator", "support", "help", "helpdesk", "noreply", "no-reply",
    "sales", "contact", "hello", "postmaster", "webmaster", "hostmaster", "abuse", "security",
    "privacy", "billing", "accounts", "careers", "jobs", "hr", "office", "team", "enquiries",
})
_EMAIL_CONTEXT = ("email", "e mail", "mail", "email address", "mail id", "email id")


def detect_emails(text: str, location, config: DetectionConfig):
    if "@" not in text:
        return
    for match in _EMAIL.finditer(text):
        local, domain, tld = match.group("local"), match.group("domain").lower(), match.group("tld").lower()
        if ".." in local or tld in _FILE_EXTENSIONS:
            continue
        # "git@github.com:org/repo.git" is an SSH remote, not a mailbox.
        if text[match.end():match.end() + 1] == ":" and text[match.end() + 1:match.end() + 2].strip():
            continue

        reasons = ["Matches the structure of an email address"]
        if domain in _RESERVED_DOMAINS or domain.endswith(tuple("." + d for d in _RESERVED_DOMAINS)) or tld in _RESERVED_TLDS:
            confidence = 0.4
            reasons.append("its domain is reserved for documentation and testing, so it is probably sample data")
        elif local.lower() in _ROLE_MAILBOXES:
            confidence = 0.5
            reasons.append("it is a shared role mailbox rather than one person's address")
        else:
            confidence = 0.9
            context = header_mentions(location, _EMAIL_CONTEXT) or label_before(text, match.start(), _EMAIL_CONTEXT)
            if context:
                confidence = 0.95
                reasons.append(f"labelled '{context}'")
        yield Detection(
            "email_address", match.start(), match.end(), match.group(), match.group().lower(),
            PATTERN, confidence, "; ".join(reasons) + ".",
        )


# ------------------------------------------------------------------ phone

_PHONE_CONTEXT = (
    "phone", "mobile", "mob", "tel", "telephone", "cell", "contact number", "contact no",
    "whatsapp", "ph", "fax", "landline", "phone number", "mobile number", "mobile no",
)


def detect_phones(text: str, location, config: DetectionConfig):
    if sum(ch.isdigit() for ch in text) < 7:  # cheap pre-check: the matcher is slow
        return
    for match in PhoneNumberMatcher(text, config.region, leniency=Leniency.VALID):
        raw = match.raw_string
        context = header_mentions(location, _PHONE_CONTEXT) or label_before(text, match.start, _PHONE_CONTEXT)
        formatted = any(ch in raw for ch in "+ -()")
        if not formatted and not context:
            # Any bare 10-digit run starting 6-9 IS a valid Indian mobile number - and
            # just as likely an invoice or order ID. Without a label, it isn't reported.
            continue
        region = phonenumbers.region_code_for_number(match.number) or "an unknown region"
        reasons = [f"A valid phone number for {region} according to its numbering plan"]
        if context:
            reasons.append(f"labelled '{context}'")
        yield Detection(
            "phone_number", match.start, match.end, raw,
            # E.164 ("+919876543210") as the key: "98765 43210" and "+91-98765-43210"
            # are the same number and group together.
            phonenumbers.format_number(match.number, PhoneNumberFormat.E164),
            VALIDATED, 0.95 if context else 0.8, "; ".join(reasons) + ".",
        )


def country_code_of(e164: str) -> str:
    """'+442079460001' -> '44'. Used by masking to keep the country code visible."""
    try:
        return str(phonenumbers.parse(e164).country_code)
    except phonenumbers.NumberParseException:
        return ""
