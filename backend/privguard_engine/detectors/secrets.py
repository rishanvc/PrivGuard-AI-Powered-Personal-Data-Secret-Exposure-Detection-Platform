"""Secrets and credentials (FR-046 to FR-055).

Evidence, strongest first:
  1. structure  - a private-key marker; a JWT whose parts decode to JSON;
  2. known formats - vendors give tokens recognisable prefixes ("AKIA",
     "ghp_", "sk_live_") precisely so that scanners can find them;
  3. context    - a value assigned to a key named like a secret
     (DB_PASSWORD=...), with placeholders such as "changeme" or
     "${DB_PASSWORD}" excluded - the main source of false alarms;
  4. randomness - entropy, only for values assigned to some setting and only
     at low confidence: hashes and IDs are random too (FR-054).

FR-055: nothing here contacts a service to test whether a credential works.
That would send the secret to a third party. A finding is a POSSIBLE secret.

Tests never contain a credential-shaped literal: they assemble one at runtime
(tests/engine/secret_fixtures.py).
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import re

from .base import CONTEXT, ENTROPY, PATTERN, VALIDATED, Detection, DetectionConfig
from .context import normalise
from .masking import looks_random, shannon_entropy

# Config-like files: an unquoted value IS the value. In code it is an expression.
CONFIG_TYPES = frozenset({"env", "config", "yaml", "json", "xml", "key"})

# ------------------------------------------------------------------ private keys (FR-051)

_PEM = re.compile(
    r"-----(?P<edge>BEGIN|END) (?P<kind>(?:RSA |DSA |EC |OPENSSH |ENCRYPTED |PGP |SSH2 )?PRIVATE KEY(?: BLOCK)?)-----"
)
_PUTTY = re.compile(r"PuTTY-User-Key-File-\d: ")


def detect_private_keys(text: str, location, config: DetectionConfig):
    if "PRIVATE KEY" in text:
        markers = list(_PEM.finditer(text))
        for i, marker in enumerate(markers):
            if marker.group("edge") != "BEGIN":
                continue
            # The key runs to its END marker - or, in a line-by-line file, to the end
            # of this line. Spanning the body means previews can never show any of it.
            following = markers[i + 1] if i + 1 < len(markers) else None
            if following is not None and following.group("edge") == "END":
                end = following.end()
            else:
                end = following.start() if following is not None else len(text)
            kind = marker.group("kind")
            reason = "A private-key block. Anyone holding it can act as its owner"
            if kind.startswith("ENCRYPTED"):
                reason += "; it is encrypted with a passphrase, which lowers but does not remove the risk"
            yield Detection("private_key", marker.start(), end, text[marker.start():end], kind, PATTERN, 0.99,
                            reason + ".")
    if "PuTTY-User-Key-File" in text:
        for match in _PUTTY.finditer(text):
            yield Detection("private_key", match.start(), len(text), text[match.start():], "putty", PATTERN, 0.99,
                            "A PuTTY private-key file. Anyone holding it can act as its owner.")


# ------------------------------------------------------------------ known formats (FR-046, FR-049, FR-050)

_START = r"(?<![A-Za-z0-9_\-])"
_END = r"(?![A-Za-z0-9_\-])"

# (type, what it is, pattern). Written from each vendor's published token format.
# A named group "secret" narrows the finding to the secret part of a longer match.
_KNOWN = [(kind, what, re.compile(pattern)) for kind, what, pattern in (
    ("cloud_credential", "an AWS access key ID", rf"{_START}(?:AKIA|ASIA|ABIA|ACCA)[A-Z2-7]{{16}}{_END}"),
    ("cloud_credential", "an Azure storage account key", r"AccountKey=(?P<secret>[A-Za-z0-9+/]{86}==)"),
    ("api_token", "a GitHub token", rf"{_START}gh[pousr]_[A-Za-z0-9]{{36}}{_END}"),
    ("api_token", "a GitHub fine-grained token", rf"{_START}github_pat_[A-Za-z0-9_]{{82}}{_END}"),
    ("api_token", "a GitLab access token", rf"{_START}glpat-[A-Za-z0-9_\-]{{20}}{_END}"),
    ("api_token", "a Slack token", rf"{_START}xox[abposr]-[A-Za-z0-9\-]{{10,250}}{_END}"),
    ("api_token", "a Slack webhook URL", r"https://hooks\.slack\.com/services/T[A-Z0-9]{8,12}/B[A-Z0-9]{8,12}/[A-Za-z0-9]{24}"),
    ("api_token", "a Stripe live secret key", rf"{_START}[rs]k_live_[A-Za-z0-9]{{24,99}}{_END}"),
    ("test_api_token", "a Stripe test-mode key", rf"{_START}[rs]k_test_[A-Za-z0-9]{{24,99}}{_END}"),
    ("api_token", "a Google API key", rf"{_START}AIza[A-Za-z0-9_\-]{{35}}{_END}"),
    ("api_token", "a Google OAuth client secret", rf"{_START}GOCSPX-[A-Za-z0-9_\-]{{28}}{_END}"),
    ("api_token", "an OpenAI API key",
     rf"{_START}sk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{{20,}}T3BlbkFJ[A-Za-z0-9_\-]{{20,}}{_END}"),
    ("api_token", "an Anthropic API key", rf"{_START}sk-ant-[a-z]+\d{{2}}-[A-Za-z0-9_\-]{{80,120}}{_END}"),
    ("api_token", "a Hugging Face token", rf"{_START}hf_[A-Za-z]{{34}}{_END}"),
    ("api_token", "an npm access token", rf"{_START}npm_[A-Za-z0-9]{{36}}{_END}"),
    ("api_token", "a PyPI API token", rf"{_START}pypi-AgEIcHlwaS5vcmc[A-Za-z0-9_\-]{{50,}}{_END}"),
    ("api_token", "a SendGrid API key", rf"{_START}SG\.[A-Za-z0-9_\-]{{22}}\.[A-Za-z0-9_\-]{{43}}{_END}"),
    ("api_token", "a Telegram bot token", r"(?<![\d:])\d{8,10}:AA[A-Za-z0-9_\-]{33}(?![A-Za-z0-9_\-])"),
    ("api_token", "a DigitalOcean token", rf"{_START}do[por]_v1_[a-f0-9]{{64}}{_END}"),
    ("api_token", "a Shopify access token", rf"{_START}shp(?:at|ca|pa|ss)_[a-fA-F0-9]{{32}}{_END}"),
)]
# Shown in a masked value: identifies the kind of token, and is the same in every token.
_PUBLIC_PREFIX = re.compile(
    r"^(?:AKIA|ASIA|ABIA|ACCA|gh[pousr]_|github_pat_|glpat-|xox[abposr]-|[rs]k_(?:live|test)_|AIza|GOCSPX-"
    r"|sk-ant-|sk-(?:proj-|svcacct-|admin-)?|hf_|npm_|pypi-|SG\.|do[por]_v1_|shp(?:at|ca|pa|ss)_"
    r"|https://hooks\.slack\.com/services/)"
)


def detect_known_secrets(text: str, location, config: DetectionConfig):
    for kind, what, pattern in _KNOWN:
        for match in pattern.finditer(text):
            group = "secret" if "secret" in pattern.groupindex else 0
            value = match.group(group)
            start, end = match.span(group)
            if "EXAMPLE" in value:  # AWS's documentation key ends in "EXAMPLE"
                yield Detection("test_api_token", start, end, value, value, PATTERN, 0.9,
                                f"Has the format of {what}, but contains 'EXAMPLE': probably documentation.")
                continue
            reason = f"Has the published format of {what}"
            if kind == "test_api_token":
                reason += "; test-mode keys cannot move real money, but still belong out of shared files"
            yield Detection(kind, start, end, value, value, PATTERN, 0.95, reason + ". Never checked against the service.")


# ------------------------------------------------------------------ JSON Web Tokens (FR-049)

_JWT = re.compile(r"(?<![A-Za-z0-9_\-.])(eyJ[A-Za-z0-9_\-]{8,})\.(eyJ[A-Za-z0-9_\-]{2,})\.([A-Za-z0-9_\-]*)(?![A-Za-z0-9_\-.])")
_ALGORITHMS = frozenset({"HS256", "HS384", "HS512", "RS256", "RS384", "RS512", "ES256", "ES384", "ES512",
                         "PS256", "PS384", "PS512", "EdDSA", "none"})
_PERSONAL_CLAIMS = ("email", "name", "given_name", "family_name", "phone_number", "birthdate", "address")


def _decode_json_part(part: str):
    try:
        decoded = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    except (ValueError, binascii.Error, RecursionError):
        return None
    return decoded if isinstance(decoded, dict) else None


def detect_jwts(text: str, location, config: DetectionConfig):
    if "eyJ" not in text:
        return
    for match in _JWT.finditer(text):
        header, payload = _decode_json_part(match.group(1)), _decode_json_part(match.group(2))
        if header is None or payload is None or not isinstance(header.get("alg"), str):
            continue  # looks like a JWT, but is not one
        algorithm = header["alg"] if header["alg"] in _ALGORITHMS else "an unrecognised algorithm"
        reason = f"A JSON Web Token: its header decodes to JSON naming the signing algorithm ({algorithm})"
        claims = [claim for claim in _PERSONAL_CLAIMS if claim in payload]
        if claims:  # claim NAMES from our own list - never their values
            reason += f"; its payload also carries personal data ({', '.join(claims)})"
        yield Detection("jwt", match.start(), match.end(), match.group(), match.group(), VALIDATED, 0.95,
                        reason + ". Anyone holding a valid token can use it until it expires.")


# ------------------------------------------------------------------ connection strings (FR-048)

_URL_CREDENTIALS = re.compile(
    r"(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]{1,20})://(?P<user>[^\s:/?#@\"'<>]{0,64}):(?P<password>[^\s@/?#\"'<>]{1,128})"
    r"@(?P<host>[A-Za-z0-9.\-_\[\]]{1,253})(?::(?P<port>\d{1,5}))?"
)
_SCHEMES = frozenset({"postgres", "postgresql", "mysql", "mariadb", "mongodb", "mongodb+srv", "redis", "rediss",
                      "amqp", "amqps", "mssql", "sqlserver", "oracle", "ftp", "sftp", "ftps", "smtp", "smtps", "http",
                      "https", "ldap", "ldaps", "ssh", "git", "jdbc"})


def detect_connection_strings(text: str, location, config: DetectionConfig):
    if "://" not in text:
        return
    for match in _URL_CREDENTIALS.finditer(text):
        password = match.group("password")
        if is_placeholder(password) or password.lower() in {"password", "pass", "secret", "pwd"}:
            continue
        scheme = match.group("scheme").lower()
        what = f"A {scheme} connection string" if scheme in _SCHEMES else "A URL"
        yield Detection("connection_string", match.start(), match.end(), match.group(), match.group(), PATTERN, 0.9,
                        f"{what} with a username and password embedded in it.")


# ------------------------------------------------------------------ Authorization headers (FR-049)

_BEARER = re.compile(r"\bBearer\s+(?P<token>[A-Za-z0-9\-._~+/]{20,}=*)")
_BASIC = re.compile(r"\bBasic\s+(?P<token>[A-Za-z0-9+/]{8,}={0,2})(?![A-Za-z0-9+/=])")


def detect_auth_headers(text: str, location, config: DetectionConfig):
    if "Bearer" in text:
        for match in _BEARER.finditer(text):
            token = match.group("token")
            if not is_placeholder(token):
                yield Detection("secret_assignment", *match.span("token"), token, token, CONTEXT, 0.8,
                                "Follows 'Bearer', as in an HTTP Authorization header: an access token.")
    if "Basic" in text:
        for match in _BASIC.finditer(text):
            try:
                decoded = base64.b64decode(match.group("token"), validate=True).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError, ValueError):
                continue
            user, colon, password = decoded.partition(":")
            if colon and password and not is_placeholder(password):
                token = match.group("token")
                yield Detection("password", *match.span("token"), token, token, VALIDATED, 0.9,
                                "HTTP Basic authentication: decodes to a username and password.")


# ------------------------------------------------------------------ secrets in configuration (FR-047, FR-052)

_ASSIGNMENT = re.compile(
    r"(?<![A-Za-z0-9_.])(?P<key>[A-Za-z_][A-Za-z0-9_.\-]{0,62})[\"']?[ \t]*(?:=|:=|:|=>)[ \t]*"
    r"(?:(?P<q>[\"'`])(?P<qvalue>[^\"'`\r\n]{1,256})(?P=q)|(?P<value>[^\s\"'`,;#<>(){}\[\]]{1,256}))"
)
_XML_ELEMENT = re.compile(r"<(?P<key>[A-Za-z_][\w.\-]{0,62})>(?P<qvalue>[^<\r\n]{1,256})</(?P=key)>")

_PASSWORD_WORDS = frozenset({"password", "passwd", "pwd", "passphrase", "passcode"})
_SECRET_WORDS = frozenset({"secret", "token", "credential", "credentials", "apikey", "privatekey", "passkey"})
_KEY_QUALIFIERS = frozenset({"api", "access", "private", "secret", "signing", "encryption", "master", "auth",
                             "app", "client", "service", "account", "session", "consumer", "webhook"})
# A last word that makes the key DESCRIBE a secret rather than hold one:
# "token_expiry", "secret_name", "password_min_length", "api_key_id".
_DESCRIPTORS = frozenset({
    "expiry", "expires", "expiration", "ttl", "timeout", "lifetime", "duration", "length", "len", "size", "limit",
    "max", "min", "count", "type", "name", "url", "uri", "endpoint", "path", "file", "dir", "header", "prefix",
    "format", "version", "id", "policy", "hint", "field", "label", "regex", "pattern", "enabled", "required",
    "hash", "algorithm", "alg", "mode", "provider", "rotation", "reset", "changed", "updated", "created", "at",
    "env", "var", "variable", "location", "store", "storage", "source", "ref",
    "seconds", "secs", "minutes", "mins", "hours", "days", "ms",
})
_NOT_SECRETS = frozenset({"csrf", "xsrf", "public", "publishable"})
# Keys naming hashes and identifiers: random by design, so entropy says nothing.
_RANDOM_BY_DESIGN = frozenset({
    "hash", "sha", "sha1", "sha256", "sha512", "md5", "checksum", "digest", "integrity", "etag", "uuid", "guid",
    "id", "commit", "revision", "rev", "version", "nonce", "salt", "fingerprint", "thumbprint", "signature", "sig",
})

_PLACEHOLDER = re.compile(
    r"^(?:true|false|yes|no|on|off|none|null|nil|undefined|empty|n/?a|tbd|todo|fixme|password|secret|pass|test)$"
    r"|change[-_ ]?me|replace[-_ ]?me|your[-_ ]|placeholder|example|dummy|sample|redacted|<.*>|x{4,}|\*{3,}|•{3,}"
    r"|^\$\{|^\$\(|^\$[A-Z_][A-Z0-9_]*$|^%.*%$|^\{\{|^#\{|^@@|^ENC\(|^vault:|^ref\+|^!secret"
    r"|os\.environ|getenv|process\.env|^env\(|ENV\[",
    re.IGNORECASE,
)
_PATHLIKE = re.compile(r"^(?:/|\./|\.\./|~/|[A-Za-z]:\\|\\\\)|\.(?:pem|key|p12|pfx|jks|json|txt|crt|env|ya?ml)$",
                       re.IGNORECASE)


def is_placeholder(value: str) -> bool:
    value = value.strip()
    return not value or bool(_PLACEHOLDER.search(value)) or len(set(value)) == 1


def _classify(key: str) -> tuple[str, str] | None:
    """(type, the word that decided it) for a key that names a secret, else None."""
    words = normalise(key).split()
    if not words or words[-1] in _DESCRIPTORS or _NOT_SECRETS.intersection(words):
        return None
    if {"aws", "secret"} <= set(words):
        return "cloud_credential", "aws secret"
    for word in words:
        if word in _PASSWORD_WORDS:
            return "password", word
    if key.lower() == "pass":
        return "password", "pass"
    for word in words:
        if word in _SECRET_WORDS:
            return "secret_assignment", word
    if "key" in words and _KEY_QUALIFIERS.intersection(words):
        return "secret_assignment", f"{sorted(_KEY_QUALIFIERS.intersection(words))[0]} key"
    return None


def _acceptable(value: str, kind: str, quoted: bool, file_type: str) -> bool:
    if is_placeholder(value) or _PATHLIKE.search(value) or value.lower().startswith(("http://", "https://")):
        return False
    if len(value) < (4 if kind == "password" else 8):
        return False
    if kind != "password" and value.isdigit() and len(value) < 12:
        return False
    if quoted or file_type in CONFIG_TYPES:
        return True
    if file_type == "code":
        return False  # unquoted in code: an expression such as request.form["password"]
    # Prose, logs, documents: "Password: reset" is a word, "Password: Welcome@123" is a password.
    return any(not ch.isalpha() for ch in value)


def _entropy_threshold(length: int) -> float:
    """Just above what camelCase identifiers with a digit score at this length (their 99th
    percentile, measured over 20,000 samples per length). Random keys clear it ~98% of the
    time at 32 characters and almost always beyond; at 20 characters the two overlap, so
    about half of short random keys are missed (D-037)."""
    return 2.88 + 0.27 * math.log2(length)


def detect_assignments(text: str, location, config: DetectionConfig):
    file_type = config.file_type
    # A spreadsheet or CSV column headed "Password": the cell holds only the value.
    header = location.get("header")
    if header:
        classified = _classify(str(header))
        value = text.strip()
        if classified is not None and _acceptable(value, classified[0], True, file_type):
            start = text.index(value)
            yield Detection(classified[0], start, start + len(value), value, value, CONTEXT, 0.85,
                            f"In a column whose header says it holds a secret ('{classified[1]}').")
            return
    if not any(sep in text for sep in "=:>"):
        return
    matches = list(_ASSIGNMENT.finditer(text))
    if "</" in text:
        matches += _XML_ELEMENT.finditer(text)
    for match in matches:
        quoted = match.group("qvalue") is not None
        group = "qvalue" if quoted else "value"
        value = match.group(group)
        start, end = match.span(group)
        stripped = value.strip()
        if stripped != value:
            start += len(value) - len(value.lstrip())
            value = stripped
            end = start + len(value)
        words = set(normalise(match.group("key")).split())
        if words & _NOT_SECRETS:
            continue  # CSRF tokens and public keys are meant to be seen
        classified = _classify(match.group("key"))

        if classified is not None:
            kind, word = classified
            if not _acceptable(value, kind, quoted, file_type):
                continue
            if kind == "cloud_credential" and not re.fullmatch(r"[A-Za-z0-9/+]{40}", value):
                kind = "secret_assignment"  # named like an AWS secret, but not shaped like one
            confidence = 0.85 if file_type in CONFIG_TYPES else 0.8 if quoted else 0.75
            yield Detection(kind, start, end, value, value, CONTEXT, confidence,
                            f"Assigned to a setting whose name says it holds a secret ('{word}').")
            continue

        # FR-054: no secret-sounding name - is the value itself random-looking?
        # Only where a value is unambiguous: config files, and string literals in code.
        if not (quoted or file_type in CONFIG_TYPES):
            continue
        if words & _RANDOM_BY_DESIGN or len(value) < 20 or not re.fullmatch(r"[A-Za-z0-9+/=_\-]+", value):
            continue
        bits = shannon_entropy(value)
        if looks_random(value) and bits >= _entropy_threshold(len(value)) and not is_placeholder(value):
            yield Detection("high_entropy_secret", start, end, value, value, ENTROPY, 0.4,
                            f"A long, random-looking value (about {bits:.1f} bits of entropy per character) assigned "
                            "to a setting. Keys and passwords look like this - but so do hashes and IDs, so this "
                            "is weak evidence.")


# ------------------------------------------------------------------ masking (FR-053)

_PEM_KIND = re.compile(r"BEGIN ([A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?)")


def mask_secret(detection: Detection) -> str:
    """Enough to tell WHAT was found and where it points - never any of the secret itself."""
    value = detection.value
    if detection.type == "private_key":
        kind = _PEM_KIND.search(value)
        return f"-----BEGIN {kind.group(1)}----- (contents not shown)" if kind else "PuTTY private key (contents not shown)"
    if detection.type == "connection_string":
        match = _URL_CREDENTIALS.match(value)
        port = f":{match.group('port')}" if match and match.group("port") else ""
        return f"{match.group('scheme')}://****:****@{match.group('host')}{port}" if match else "****"
    if detection.type == "jwt":
        return "eyJ****.eyJ****.****"
    if detection.type in ("cloud_credential", "api_token", "test_api_token"):
        prefix = _PUBLIC_PREFIX.match(value)
        return (prefix.group() if prefix else "") + "****"
    return "********"  # passwords and values from settings: not even their length
