"""File-type detection by content, not by name (FR-012, FR-013, NFR-009).

Pure Python - no Django. Given a filename and a readable, seekable binary
stream, decide whether PrivGuard can process the file, and if not, why.

Validation is not a safety guarantee. A file can be valid as two formats at
once (a "polyglot"). PrivGuard's safety comes from never executing content
(NFR-011); this module keeps mislabelled or unprocessable files out of the
pipeline and gives the user a clear reason.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import BinaryIO

# Bump when classification rules change, so each scan records which rules
# inventoried it (kept in Scan.configuration; reported per FR-108).
INTAKE_VERSION = 1

SNIFF_BYTES = 8192
MAX_OOXML_PARTS = 10_000
_MB = 1024 * 1024


class Verdict(str, Enum):
    SUPPORTED = "supported"      # PrivGuard can process this file
    UNSUPPORTED = "unsupported"  # recognised or unknown, but not processable
    REJECTED = "rejected"        # failed validation: too large, mislabelled, malformed


@dataclass(frozen=True)
class Inspection:
    verdict: Verdict
    file_type: str = ""  # e.g. "pdf", "docx", "code", "env"; "" when unknown
    reason: str = ""     # fixed wording; never includes file content


# ------------------------------------------------------------------ text formats

# Extension -> kind. Kinds are coarse on purpose: Cycle 4 routes extraction by
# kind (CSV vs structured vs plain text), and FR-087 filters by file type.
_TEXT_KINDS: dict[str, tuple[str, ...]] = {
    "text": ("txt", "log", "md", "rst"),
    "csv": ("csv", "tsv"),
    "json": ("json", "jsonl", "ndjson"),
    "yaml": ("yaml", "yml"),
    "xml": ("xml",),
    "env": ("env",),
    "config": ("ini", "cfg", "conf", "config", "properties", "toml", "tf", "tfvars", "hcl"),
    "key": ("pem", "key", "crt", "cer", "pub", "asc"),
    "code": (
        "py", "js", "jsx", "mjs", "cjs", "ts", "tsx", "java", "kt", "kts", "scala",
        "go", "rb", "php", "cs", "c", "h", "cpp", "cc", "hpp", "rs", "swift", "m",
        "dart", "lua", "pl", "r", "sh", "bash", "zsh", "ps1", "psm1", "bat", "cmd",
        "sql", "gradle", "html", "htm", "css", "scss", "less", "vue", "svelte",
        "graphql", "proto",
    ),
}
TEXT_EXTENSIONS = {ext: kind for kind, exts in _TEXT_KINDS.items() for ext in exts}

# UTF-16/32 text legitimately contains NUL bytes; a byte-order mark marks it as text.
_WIDE_BOMS = (b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff", b"\xff\xfe", b"\xfe\xff")


# ------------------------------------------------------------------ binary formats

_ZIP = b"PK\x03\x04"
_NO_OCR_YET = "Image text extraction (OCR) is not available yet."


@dataclass(frozen=True)
class _BinaryFormat:
    file_type: str
    label: str                     # used in user-facing reasons
    signatures: tuple[bytes, ...]
    supported: bool
    unsupported_reason: str = ""
    ooxml_part: str | None = None  # part that must exist inside an Office Open XML file
    search_window: int = 0         # >0: signature may appear anywhere in the first N bytes


_BINARY: dict[str, _BinaryFormat] = {
    # The PDF spec tolerates bytes before the header, so search the first 1 KB.
    "pdf": _BinaryFormat("pdf", "PDF", (b"%PDF-",), True, search_window=1024),
    "docx": _BinaryFormat("docx", "Word document", (_ZIP,), True, ooxml_part="word/document.xml"),
    "xlsx": _BinaryFormat("xlsx", "Excel workbook", (_ZIP,), True, ooxml_part="xl/workbook.xml"),
    # Recognised, but not processable yet. Flipping `supported` later turns on
    # the signature and structure checks below with no other change.
    "pptx": _BinaryFormat(
        "pptx", "PowerPoint presentation", (_ZIP,), False,
        "PowerPoint files are not supported yet.", ooxml_part="ppt/presentation.xml",
    ),
    "png": _BinaryFormat("png", "PNG image", (b"\x89PNG\r\n\x1a\n",), False, _NO_OCR_YET),
    "jpg": _BinaryFormat("jpeg", "JPEG image", (b"\xff\xd8\xff",), False, _NO_OCR_YET),
    "jpeg": _BinaryFormat("jpeg", "JPEG image", (b"\xff\xd8\xff",), False, _NO_OCR_YET),
}

_ARCHIVES = frozenset({"zip", "tar", "gz", "tgz", "bz2", "xz", "7z", "rar"})
_ARCHIVE_REASON = "Archives are not supported yet. Upload the extracted files or the folder instead."

# What a file's first bytes suggest it really is. Used only to EXPLAIN a
# mismatch, e.g. "named .pdf, but the content looks like a Windows executable".
_CONTENT_HINTS: tuple[tuple[bytes, str], ...] = (
    (b"MZ", "a Windows executable"),
    (b"\x7fELF", "a Linux executable"),
    (b"\xcf\xfa\xed\xfe", "a macOS executable"),
    (_ZIP, "a ZIP archive"),
    (b"%PDF-", "a PDF"),
    (b"\x89PNG\r\n\x1a\n", "a PNG image"),
    (b"\xff\xd8\xff", "a JPEG image"),
    (b"\x1f\x8b", "a gzip archive"),
    (b"Rar!", "a RAR archive"),
    (b"7z\xbc\xaf\x27\x1c", "a 7-Zip archive"),
)


# ------------------------------------------------------------------ public API

def inspect_file(name: str, stream: BinaryIO, size: int, max_bytes: int) -> Inspection:
    """Classify one file. `name` should already be sanitised (see names.py).

    Reads at most SNIFF_BYTES, plus the ZIP table of contents for Office files.
    Never decompresses anything. Leaves the stream positioned at 0.
    """
    if size > max_bytes:
        # Decided from the size alone: the file is never read.
        return Inspection(Verdict.REJECTED, reason=f"File exceeds the per-file limit of {_mb(max_bytes)}.")

    ext = _extension(name)

    if ext in _ARCHIVES:
        return Inspection(Verdict.UNSUPPORTED, "archive", _ARCHIVE_REASON)

    fmt = _BINARY.get(ext)
    if fmt is not None and not fmt.supported:
        return Inspection(Verdict.UNSUPPORTED, fmt.file_type, fmt.unsupported_reason)

    try:
        stream.seek(0)
        head = stream.read(SNIFF_BYTES)

        if fmt is not None:
            return _inspect_binary(fmt, ext, head, stream)

        kind = _text_kind(name, ext)
        if kind is not None:
            return _inspect_text(kind, head)

        if not ext:
            # Extensionless: Dockerfile, Makefile, id_rsa, .npmrc, .gitconfig...
            if _looks_like_text(head):
                return Inspection(Verdict.SUPPORTED, "text")
            return Inspection(Verdict.UNSUPPORTED, reason="Unrecognised binary file.")

        return Inspection(Verdict.UNSUPPORTED, reason="This file type is not supported.")
    finally:
        stream.seek(0)


def supported_extensions() -> list[str]:
    """Extensions PrivGuard can process (plus .env* and extensionless text files)."""
    binary = {ext for ext, fmt in _BINARY.items() if fmt.supported}
    return sorted(set(TEXT_EXTENSIONS) | binary)


# ------------------------------------------------------------------ helpers

def _extension(name: str) -> str:
    # PurePosixPath(".env").suffix is "" - dotfiles count as extensionless.
    return PurePosixPath(name).suffix.lower().lstrip(".")


def _text_kind(name: str, ext: str) -> str | None:
    lowered = name.lower()
    if lowered == ".env" or lowered.startswith(".env."):  # .env.local, .env.production
        return "env"
    return TEXT_EXTENSIONS.get(ext)


def _looks_like_text(head: bytes) -> bool:
    """Git's heuristic: a NUL byte near the start means binary."""
    if head.startswith(_WIDE_BOMS):
        return True
    if head.startswith(b"%PDF-"):  # PDFs often have no NUL bytes in their first 8 KB
        return False
    return b"\x00" not in head


def _describe(head: bytes) -> str | None:
    for signature, description in _CONTENT_HINTS:
        if head.startswith(signature):
            return description
    return None


def _inspect_text(kind: str, head: bytes) -> Inspection:
    if _looks_like_text(head):
        return Inspection(Verdict.SUPPORTED, kind)
    actual = _describe(head)
    detail = f"the content looks like {actual}" if actual else "it contains binary data"
    return Inspection(Verdict.REJECTED, kind, f"Expected a text file, but {detail}.")


def _inspect_binary(fmt: _BinaryFormat, ext: str, head: bytes, stream: BinaryIO) -> Inspection:
    if fmt.search_window:
        matched = any(sig in head[: fmt.search_window] for sig in fmt.signatures)
    else:
        matched = any(head.startswith(sig) for sig in fmt.signatures)

    if not matched:
        actual = _describe(head)
        detail = f"the content looks like {actual}" if actual else f"the content is not a valid {fmt.label}"
        return Inspection(Verdict.REJECTED, fmt.file_type, f"Named .{ext}, but {detail}.")

    if fmt.ooxml_part:
        problem = _check_ooxml(stream, fmt, ext)
        if problem:
            return Inspection(Verdict.REJECTED, fmt.file_type, problem)

    return Inspection(Verdict.SUPPORTED, fmt.file_type)


def _check_ooxml(stream: BinaryIO, fmt: _BinaryFormat, ext: str) -> str | None:
    """Office Open XML files are ZIPs with required parts. Check the parts exist."""
    stream.seek(0)
    try:
        # Reads only the ZIP's central directory (its table of contents).
        # Nothing is decompressed, so a zip bomb cannot expand here.
        with zipfile.ZipFile(stream) as archive:
            names = archive.namelist()
    except Exception:  # untrusted input: any parse failure means "malformed", never a crash
        return f"The file is damaged or is not a real {fmt.label}."

    if len(names) > MAX_OOXML_PARTS:
        return f"The {fmt.label} has an unusually large number of internal parts."

    present = set(names)
    if "[Content_Types].xml" not in present or fmt.ooxml_part not in present:
        return f"Named .{ext}, but it is a ZIP archive without the parts of a {fmt.label}."
    return None


def _mb(num_bytes: int) -> str:
    return f"{num_bytes / _MB:g} MB"
