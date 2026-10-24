"""Values identified by what LABELS them (FR-033, FR-034, FR-035, FR-037, FR-038).

Dates of birth, people's names, personal-record fields and addresses have no
reliable shape of their own: "17/05/1990" is a birthday only after "DOB:".
Cycle 5 decision: names come from context rules, not a machine-learning model,
so a name in free-flowing prose with nothing labelling it is NOT found. That
gap is measured, not hidden - see tests/engine/detection_corpus.py.
"""

from __future__ import annotations

import datetime
import re

from .base import CONTEXT, Detection, DetectionConfig
from .context import header_is, header_mentions, label_before, label_regex, normalise

# ------------------------------------------------------------------ shared pieces

_LETTERS = r"[^\W\d_]"                                    # any letter, any script
_WORD = rf"{_LETTERS}+(?:['’-]{_LETTERS}+)*"           # O'Brien, Anne-Marie
_CAPITALISED = rf"[A-Z]{_LETTERS}*(?:['’-]{_LETTERS}+)*"
_HONORIFICS = r"(?:Mr|Mrs|Ms|Miss|Dr|Prof|Shri|Sri|Smt|Kumari|Kum)"
_PLACEHOLDERS = frozenset({"n a", "na", "none", "null", "nil", "unknown", "test", "tbd", "tba", "not applicable", "x", "xx", "xxx", "-", "--"})


def _is_placeholder(value: str) -> bool:
    return normalise(value) in _PLACEHOLDERS or not value.strip(" -_./")


# ------------------------------------------------------------------ dates of birth

_DOB_CONTEXT = ("dob", "d o b", "date of birth", "birth date", "birthdate", "born", "born on", "birthday")
_MONTHS = {m: i for i, names in enumerate(
    (("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",), ("jun", "june"),
     ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
     ("dec", "december")), start=1) for m in names}
_MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_YEAR = r"(?:19|20)\d{2}"
_DATE = re.compile(
    rf"(?<!\d)(?:"
    rf"(?P<iy>{_YEAR})-(?P<im>\d{{1,2}})-(?P<id>\d{{1,2}})(?:T[\d:.]+)?"                       # 1990-05-17
    rf"|(?P<nd>\d{{1,2}})[/.-](?P<nm>\d{{1,2}})[/.-](?P<ny>{_YEAR})"                           # 17/05/1990
    rf"|(?P<td>\d{{1,2}})(?:st|nd|rd|th)?[\s-]+(?P<tm>{_MONTH})\.?,?[\s-]+(?P<ty>{_YEAR})"     # 3 March 1985
    rf"|(?P<um>{_MONTH})\.?\s+(?P<ud>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<uy>{_YEAR})"           # March 3, 1985
    rf")(?!\d)",
    re.IGNORECASE,
)


def _as_date(match: re.Match) -> datetime.date | None:
    g = match.groupdict()
    try:
        if g["iy"]:
            return datetime.date(int(g["iy"]), int(g["im"]), int(g["id"]))
        if g["ny"]:
            day, month, year = int(g["nd"]), int(g["nm"]), int(g["ny"])
            try:
                return datetime.date(year, month, day)        # India writes day first...
            except ValueError:
                return datetime.date(year, day, month)        # ...but accept month-first too
        # Every spelling _MONTH accepts ("Mar", "March", "Sept", ...) is a key of _MONTHS.
        if g["ty"]:
            return datetime.date(int(g["ty"]), _MONTHS[g["tm"].lower()], int(g["td"]))
        return datetime.date(int(g["uy"]), _MONTHS[g["um"].lower()], int(g["ud"]))
    except (ValueError, KeyError):
        return None


def detect_dates_of_birth(text: str, location, config: DetectionConfig):
    in_dob_column = header_mentions(location, _DOB_CONTEXT)
    for match in _DATE.finditer(text):
        context = in_dob_column or label_before(text, match.start(), _DOB_CONTEXT, window=30)
        if not context:
            continue  # a date is only a birthday when something says so
        date = _as_date(match)
        if date is None or not datetime.date(1900, 1, 1) <= date <= datetime.date.today():
            continue
        yield Detection("date_of_birth", match.start(), match.end(), match.group(), date.isoformat(), CONTEXT, 0.9,
                        f"A valid date labelled '{context}'.")


# ------------------------------------------------------------------ people's names

# A column is a NAME column only if its header is exactly one of these.
# 'File name', 'Host name', 'Company name' all end in "name" - none is a person.
_NAME_COLUMNS = frozenset({
    "name", "full name", "first name", "last name", "surname", "given name", "family name", "middle name",
    "maiden name", "employee name", "emp name", "staff name", "customer name", "client name", "patient name",
    "student name", "contact name", "contact person", "account holder", "account holder name", "holder name",
    "applicant name", "candidate name", "member name", "guardian name", "father name", "fathers name",
    "father s name", "mother name", "mothers name", "mother s name", "spouse name", "nominee name",
    "beneficiary name", "person name",
})
# For a bare "Name:" label, the word before it decides. "File name: report.pdf" is not a person.
_NOT_PEOPLE = frozenset({
    "file", "user", "host", "company", "product", "project", "domain", "sheet", "server", "bank", "branch",
    "brand", "field", "column", "table", "app", "application", "device", "path", "class", "variable", "street",
    "city", "town", "village", "district", "state", "country", "school", "college", "hospital", "organisation",
    "organization", "business", "shop", "store", "team", "group", "event", "course", "item", "test", "job",
    "task", "role", "display", "screen", "account", "package", "module", "function", "method", "service",
    "queue", "topic", "bucket", "key", "folder", "directory", "model", "tag", "category", "plan", "scheme",
    "policy", "database", "db", "schema", "index", "container", "image", "repo", "repository",
})
_NOT_A_NAME = frozenset({
    "sir", "madam", "sir madam", "customer", "customers", "colleague", "colleagues", "all", "team", "friend",
    "friends", "member", "members", "user", "users", "applicant", "candidate", "valued customer",
    "hiring manager", "recruiter", "student", "students", "parent", "parents",
})
_AUTHOR_FIELDS = frozenset({"creator", "lastModifiedBy", "author", "Manager"})
# Words that usually START another field. Forms and PDF text often run fields
# together on one line - "Customer Name: Neha Gupta Order ID: 4421" - and a
# name must stop where the next field begins.
_FIELD_WORDS = frozenset({
    "order", "invoice", "ref", "reference", "id", "no", "number", "code", "date", "dob", "age", "gender",
    "sex", "phone", "mobile", "tel", "ph", "email", "mail", "address", "addr", "city", "state", "pin",
    "pincode", "pan", "aadhaar", "account", "amount", "total", "employee", "emp", "dept", "department",
    "designation", "role", "status", "branch", "customer", "policy", "claim", "ticket", "item", "qty", "price",
})

_NAME_LABEL = label_regex(_NAME_COLUMNS)
_NAME_AFTER_LABEL = re.compile(rf"(?:{_HONORIFICS}\.?\s+)?(?P<name>{_WORD}(?:[ ]{_WORD}){{0,4}})")
_SALUTATION = re.compile(rf"\bDear\s+(?:{_HONORIFICS}\.?\s+)?(?P<name>{_CAPITALISED}(?:\s{_CAPITALISED}){{0,3}})")
_TITLED = re.compile(rf"(?<!\w){_HONORIFICS}\.?\s+(?P<name>{_CAPITALISED}(?:\s{_CAPITALISED}){{0,3}})")
_NAME_SHAPE = re.compile(rf"{_WORD}(?:[ .]+{_WORD}){{0,4}}\.?")
_COLON_NEXT = re.compile(r"[ \t]*:")
# "Name", "Surname": a blank form's own labels are not anyone's name either.
_NEVER_NAMES = _NOT_A_NAME | _NAME_COLUMNS


def _name_like(value: str) -> bool:
    value = value.strip()
    if not value or len(value) > 60 or _is_placeholder(value) or "@" in value:
        return False
    if any(ch.isdigit() for ch in value) or normalise(value) in _NEVER_NAMES:
        return False
    return _NAME_SHAPE.fullmatch(value) is not None


def _whole_value(text: str, type_: str, confidence: float, explanation: str) -> Detection:
    value = text.strip()
    start = text.index(value)
    return Detection(type_, start, start + len(value), value, value.casefold(), CONTEXT, confidence, explanation)


def detect_person_names(text: str, location, config: DetectionConfig):
    # 1. Document metadata and comment authors: whoever is recorded there.
    if location.get("field") in _AUTHOR_FIELDS:
        if text.strip() and not _is_placeholder(text):
            yield _whole_value(text, "person_name", 0.85,
                               "Recorded as the document's author or a commenter; it may be a full name or a username.")
        return
    # 2. A cell in a column for names.
    column = header_is(location, _NAME_COLUMNS)
    if column:
        if _name_like(text):
            yield _whole_value(text, "person_name", 0.85, f"In a column headed '{column}'.")
        return
    # 3. Labels, salutations and titles in running text.
    yield from _labelled_names(text)
    yield from _titled_names(text, _SALUTATION, 0.75, "Follows the salutation 'Dear'.")
    yield from _titled_names(text, _TITLED, 0.7, "Follows a title such as Mr, Ms, Dr or Smt.")


def _labelled_names(text: str):
    for label in _NAME_LABEL.finditer(text):
        phrase = normalise(label.group("label"))
        if phrase == "name":
            before = normalise(text[max(0, label.start() - 24):label.start()]).split()
            if before and before[-1] in _NOT_PEOPLE:
                continue
        found = _NAME_AFTER_LABEL.match(text, label.end())
        if not found or _NAME_LABEL.match(text, found.start("name")):
            continue  # nothing, or the next label: a blank form ("First Name: Last Name:")
        start = found.start("name")
        end = _trim_name(text, start, found.end("name"))
        name = text[start:end] if end is not None else ""
        if _name_like(name):
            yield Detection("person_name", start, end, name, name.casefold(), CONTEXT, 0.8,
                            f"Follows the label '{phrase}'.")


def _trim_name(text: str, start: int, end: int) -> int | None:
    """Where a run of words that looks like a name really ends; None if no name is left."""
    words = text[start:end].split(" ")
    # 1. Another field begins inside the run: "Neha Gupta Order ID: 4421".
    for i in range(1, len(words)):
        if words[i].lower().rstrip(".:") in _FIELD_WORDS:
            words = words[:i]
            break
    # 2. A word directly followed by ':' is the next label: "Ana Example Date: 2026".
    # Checked with a regex AT a position: slicing off the rest of the line here
    # made long lines quadratic.
    while words and _COLON_NEXT.match(text, start + len(" ".join(words))):
        words.pop()
    return start + len(" ".join(words)) if words else None


def _titled_names(text: str, pattern: re.Pattern, confidence: float, explanation: str):
    for match in pattern.finditer(text):
        start = match.start("name")
        end = _trim_name(text, start, match.end("name"))
        name = text[start:end] if end is not None else ""
        if name and normalise(name) not in _NOT_A_NAME:
            yield Detection("person_name", start, end, name, name.casefold(), CONTEXT, confidence, explanation)


# ------------------------------------------------------------------ personal-record fields (FR-037)

_RECORD_FIELDS = {
    "employee_id": ("employee id", "employee no", "employee number", "employee code", "emp id", "emp no",
                    "emp code", "staff id", "staff no", "staff number", "payroll id", "personnel number"),
    "passport_number": ("passport no", "passport number", "passport"),
    "voter_id": ("voter id", "voter id number", "epic no", "epic number", "epic"),
    "driving_licence": ("driving licence", "driving license", "driving licence no", "driving license no",
                        "dl no", "dl number", "licence no", "license no"),
    "gender": ("gender", "sex"),
    "nationality": ("nationality", "citizenship"),
    "religion_or_caste": ("religion", "caste", "sub caste"),
    "marital_status": ("marital status", "civil status"),
    "blood_group": ("blood group", "blood type"),
}
_NEEDS_DIGIT = frozenset({"employee_id", "passport_number", "voter_id", "driving_licence"})
_SPECIAL_CATEGORY = frozenset({"religion_or_caste"})
_RECORD_LABELS = {field: label_regex(phrases) for field, phrases in _RECORD_FIELDS.items()}
_RECORD_VALUE = re.compile(r"(?P<value>[^\s,;|\"']{1,40}(?: [^\s,;|\"':]{1,40}){0,2})")


def _record_value_ok(field: str, value: str) -> bool:
    if not value or len(value) > 64 or _is_placeholder(value):
        return False
    if field in _NEEDS_DIGIT:  # "Passport photo: attached" is not a passport number
        return any(ch.isdigit() for ch in value)
    return len(value) <= 30 and any(ch.isalpha() for ch in value)


def _record_reason(field: str, where: str) -> str:
    reason = f"{where}."
    if field in _SPECIAL_CATEGORY:
        reason += " Religion and caste are special-category data: especially sensitive under data-protection law."
    return reason


def detect_record_fields(text: str, location, config: DetectionConfig):
    for field, phrases in _RECORD_FIELDS.items():
        column = header_is(location, phrases)
        if column:
            if _record_value_ok(field, text.strip()):
                yield _whole_value(text, field, 0.8, _record_reason(field, f"In a column headed '{column}'"))
            return
    for field, regex in _RECORD_LABELS.items():
        for label in regex.finditer(text):
            found = _RECORD_VALUE.match(text, label.end())
            if not found:
                continue
            value = found.group("value").strip()
            if field in _NEEDS_DIGIT:
                value = value.split(" ")[0]  # identifiers are a single token
            if _record_value_ok(field, value):
                start = found.start("value")
                yield Detection(field, start, start + len(value), value, value.casefold(), CONTEXT, 0.75,
                                _record_reason(field, f"Follows the label '{normalise(label.group('label'))}'"))


# ------------------------------------------------------------------ addresses and PIN codes (FR-033)

_ADDRESS_WORDS = frozenset({"address", "addr", "address1", "address2"})
# Addresses that are not where someone lives.
_NOT_POSTAL = frozenset({"email", "e", "mail", "ip", "mac", "web", "server", "wallet", "url", "host",
                         "network", "ipv4", "ipv6", "bitcoin", "ethereum", "contract", "memory", "hardware"})
_ADDRESS_LABEL = re.compile(r"(?<![\w])(?:(?P<qualifier>[A-Za-z-]+)[ _])?(?P<label>address|addr)\b\s*[:=\-]\s*"
                            r"(?P<value>[^\n;|]{6,120})", re.IGNORECASE)
_PIN = re.compile(r"(?<!\d)([1-9]\d{2}) ?(\d{3})(?!\d)")
_PIN_CONTEXT = ("pin", "pincode", "pin code", "postal code", "postcode", "post code", "zip", "zip code")


def _postal_header(location) -> bool:
    words = set(normalise(str(location.get("header") or "")).split())
    return bool(words & _ADDRESS_WORDS) and not words & _NOT_POSTAL


def detect_addresses(text: str, location, config: DetectionConfig):
    if _postal_header(location):
        value = text.strip()
        if len(value) >= 6 and any(ch.isalpha() for ch in value) and "@" not in value:
            yield _whole_value(text, "postal_address", 0.85, "In a column headed as an address.")
            return
    for match in _ADDRESS_LABEL.finditer(text):
        qualifier = (match.group("qualifier") or "").lower()
        value = match.group("value").strip()
        if qualifier in _NOT_POSTAL or "@" in value or not any(ch.isalpha() for ch in value):
            continue
        start = match.start("value") + (len(match.group("value")) - len(match.group("value").lstrip()))
        yield Detection("postal_address", start, start + len(value), value, normalise(value), CONTEXT, 0.85,
                        "Follows an address label.")
    for match in _PIN.finditer(text):
        context = header_mentions(location, _PIN_CONTEXT) or label_before(text, match.start(), _PIN_CONTEXT, window=20)
        if context:
            yield Detection("postal_code", match.start(), match.end(), match.group(), match.group(1) + match.group(2),
                            CONTEXT, 0.85, f"A six-digit Indian PIN code labelled '{context}'.")
