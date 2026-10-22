"""Making uploaded names safe to display and record (NFR-012).

Uploaded names are attacker-controlled. PrivGuard never uses them to build a
storage path - files are stored under random names - so these functions are
about safe DISPLAY, and an honest record of where a file sat in the upload.
"""

from __future__ import annotations

import re
import unicodedata

MAX_NAME_LENGTH = 255
MAX_PATH_LENGTH = 1024
MAX_PATH_DEPTH = 64

# Bidirectional-text controls. U+202E (RIGHT-TO-LEFT OVERRIDE) makes
# "invoice\u202efdp.exe" DISPLAY as "invoiceexe.pdf": an executable
# disguised as a PDF.
_BIDI_CONTROLS = frozenset(
    "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
)
_BOM = "\ufeff"
_DRIVE_LETTER = re.compile(r"^[A-Za-z]:")


class UnsafePath(ValueError):
    """A relative path that cannot be recorded safely. The message is user-facing."""


def clean_display_text(text: str, max_length: int = MAX_NAME_LENGTH) -> str:
    """NFC-normalise, drop control characters and bidi controls, and truncate."""
    return _truncate(_strip_unsafe(text), max_length)


def display_name(raw: str) -> str:
    """The base name of an uploaded file, safe to show. Never a path.

    "C:\\Users\\alice\\secret.txt" -> "secret.txt": absolute paths are never
    kept (SRS 7.2.3).
    """
    base = raw.replace("\\", "/").rsplit("/", 1)[-1]
    name = clean_display_text(base)
    return name if name not in ("", ".", "..") else "unnamed"


def safe_relative_path(raw: str) -> str:
    """Validate a folder-upload path such as "src/config/.env".

    Returns a normalised path with "/" separators, or raises UnsafePath.
    Rejects traversal, absolute and drive-letter paths, NUL bytes, and
    components that are empty once invisible characters are removed.
    """
    if "\x00" in raw:
        raise UnsafePath("The path contains a NUL character.")

    unified = raw.replace("\\", "/")
    if unified.startswith("/"):  # also catches UNC paths: //server/share
        raise UnsafePath("Absolute paths are not allowed.")
    if _DRIVE_LETTER.match(unified):
        raise UnsafePath("Paths with a drive letter are not allowed.")

    parts: list[str] = []
    for raw_part in unified.split("/"):
        if raw_part in ("", "."):  # collapse "a//b" and "./a"
            continue
        # Clean BEFORE checking for "..": ".\u202e." becomes ".." once the
        # invisible character is removed.
        part = _strip_unsafe(raw_part)
        if part == "..":
            raise UnsafePath("Path traversal ('..') is not allowed.")
        if part in ("", "."):
            raise UnsafePath("The path contains an invisible or empty component.")
        if len(part) > MAX_NAME_LENGTH:
            raise UnsafePath("A path component is too long.")
        parts.append(part)

    if not parts:
        raise UnsafePath("The path is empty.")
    if len(parts) > MAX_PATH_DEPTH:
        raise UnsafePath("The path is nested too deeply.")

    path = "/".join(parts)
    if len(path) > MAX_PATH_LENGTH:
        raise UnsafePath("The path is too long.")
    return path


def _strip_unsafe(text: str) -> str:
    """Remove characters that are invisible or can disguise a name.

    Deliberately KEEPS U+200C/U+200D (zero-width non-joiner/joiner). They are
    invisible format characters, but Persian and Indic scripts need them to
    render words correctly - stripping every invisible character would
    corrupt legitimate filenames.
    """
    text = unicodedata.normalize("NFC", text)
    return "".join(
        ch for ch in text
        if ch not in _BIDI_CONTROLS and ch != _BOM and unicodedata.category(ch) != "Cc"
    ).strip()


def _truncate(text: str, max_length: int) -> str:
    """Shorten to max_length, keeping a short extension visible."""
    if len(text) <= max_length:
        return text
    stem, dot, ext = text.rpartition(".")
    if dot and stem and 0 < len(ext) <= 16:
        keep = max_length - len(ext) - 2  # room for the ellipsis and the dot
        return f"{stem[:keep]}\u2026.{ext}"
    return text[: max_length - 1] + "\u2026"
