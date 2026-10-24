"""Local OCR with Tesseract (FR-023, FR-027). Runs inside the isolated extraction child.

Tesseract (Apache-2.0) is a separate program, run as a subprocess with a time
limit - never a library linked into PrivGuard. It reads PNG, JPEG and the PGM
files written here for scanned PDF pages, and returns every word with its
position and a confidence of 0-100 (TSV output). Nothing here uses the network.

Images are hostile input like any other file: a tiny PNG can claim to be
50,000 x 50,000 pixels, and decoding it would need gigabytes of memory. So an
image's size is read from its header BEFORE Tesseract sees it.
"""

from __future__ import annotations

import os
import struct
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass

from .base import ExtractionError, NotSupported


@dataclass(frozen=True)
class OcrConfig:
    command: str                      # full path to tesseract.exe
    languages: str = "eng"
    dpi: int = 300                    # resolution scanned PDF pages are rendered at
    max_pixels: int = 40_000_000      # about an A3 page at 300 DPI
    max_pages: int = 50               # scanned pages OCR'd per PDF
    time_budget: float = 90.0         # seconds of OCR per file - below the child's 120 s timeout
    temp_dir: str = ""                # private folder for rendered pages (FR-030)


@dataclass(frozen=True)
class OcrLine:
    text: str
    box: tuple[int, int, int, int]    # left, top, width, height - in pixels of the image read
    confidence: float                 # mean of the words' confidences, 0-100


class OcrBudget:
    """The seconds of OCR a file may still use."""

    def __init__(self, seconds: float):
        self.deadline = time.monotonic() + seconds

    def remaining(self) -> float:
        return self.deadline - time.monotonic()


# ------------------------------------------------------------------ image headers

_PNG = b"\x89PNG\r\n\x1a\n"
# JPEG "start of frame" markers carry the size; C4 (Huffman), C8 and CC (arithmetic coding) are not frames.
_JPEG_FRAMES = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}


def image_size(path: str) -> tuple[int, int]:
    """(width, height) from a PNG or JPEG header - without decoding a single pixel."""
    with open(path, "rb") as handle:
        head = handle.read(32)
        if head.startswith(_PNG) and head[12:16] == b"IHDR":
            return struct.unpack(">II", head[16:24])
        if head.startswith(b"\xff\xd8"):
            return _jpeg_size(handle)
    raise ExtractionError("The image is damaged or is not a PNG or JPEG image.")


def _jpeg_size(handle) -> tuple[int, int]:
    handle.seek(2)
    for _ in range(10_000):  # bounded: a hostile file cannot make this loop forever
        marker = handle.read(2)
        if len(marker) < 2 or marker[0] != 0xFF:
            break
        if marker[1] in (0xD8, 0x01) or 0xD0 <= marker[1] <= 0xD7:
            continue  # markers without a length field
        length_bytes = handle.read(2)
        if len(length_bytes) < 2:
            break
        length = struct.unpack(">H", length_bytes)[0]
        if marker[1] in _JPEG_FRAMES:
            frame = handle.read(5)
            if len(frame) == 5:
                height, width = struct.unpack(">HH", frame[1:5])
                return width, height
            break
        handle.seek(length - 2, os.SEEK_CUR)
    raise ExtractionError("The JPEG image is damaged: its size could not be read.")


def check_pixels(width: int, height: int, config: OcrConfig) -> None:
    if width <= 0 or height <= 0:
        raise ExtractionError("The image reports no size, so it cannot be read.")
    if width * height > config.max_pixels:
        raise NotSupported(
            f"The image is too large to read safely ({width:,} x {height:,} pixels; the limit is "
            f"{config.max_pixels // 1_000_000} million)."
        )


# ------------------------------------------------------------------ rendered pages

def write_pgm(path: str, width: int, height: int, stride: int, pixels: bytes) -> None:
    """A grayscale image in PGM, the simplest format Tesseract reads: a short text
    header, then one byte per pixel. Rows in a rendered bitmap may be padded to
    `stride` bytes; only the first `width` bytes of each row are pixels."""
    with open(path, "wb") as handle:
        handle.write(f"P5\n{width} {height}\n255\n".encode("ascii"))
        for row in range(height):
            start = row * stride
            handle.write(pixels[start:start + width])


def temp_image_path(config: OcrConfig, suffix: str = ".pgm") -> str:
    """A random name in the private temp folder: rendered pages show the user's documents.
    The worker always passes PrivGuard's own var/tmp; only the command-line tools fall back
    to the system's temporary folder."""
    return os.path.join(config.temp_dir or tempfile.gettempdir(), f"ocr-{uuid.uuid4().hex}{suffix}")


# ------------------------------------------------------------------ running Tesseract

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows: no console window flashes up


def run_tesseract(image_path: str, config: OcrConfig, timeout: float, *, dpi: int | None = None) -> list[OcrLine]:
    """OCR one image. Raises ExtractionError if Tesseract fails or runs out of time."""
    if timeout <= 0:
        raise ExtractionError("OCR stopped: the time allowed for reading this file ran out.")
    command = [config.command, image_path, "stdout", "-l", config.languages, "tsv"]
    if dpi:
        command[3:3] = ["--dpi", str(dpi)]
    try:
        completed = subprocess.run(
            command, capture_output=True, timeout=timeout, check=False, creationflags=_NO_WINDOW,
            # One thread keeps memory and CPU predictable on a small machine.
            env={**os.environ, "OMP_THREAD_LIMIT": "1"},
        )
    except subprocess.TimeoutExpired:  # subprocess.run kills Tesseract before raising this
        raise ExtractionError("OCR stopped: the time allowed for reading this file ran out.") from None
    except OSError:
        raise ExtractionError("OCR is configured, but the Tesseract program could not be started.") from None
    if completed.returncode != 0:
        # Tesseract's own message is not repeated: it can name paths, and is not for users.
        raise ExtractionError("OCR could not read this image. It may be damaged or in an unusual format.")
    return parse_tsv(completed.stdout.decode("utf-8", errors="replace"))


def parse_tsv(tsv: str) -> list[OcrLine]:
    """Tesseract's TSV: one row per word (level 5), grouped here into lines in reading order."""
    lines: dict[tuple[str, ...], list[tuple[str, int, int, int, int, float]]] = {}
    for row in tsv.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) != 12 or cols[0] != "5" or not cols[11].strip():
            continue
        try:
            left, top, width, height = (int(v) for v in cols[6:10])
            confidence = float(cols[10])
        except ValueError:
            continue
        if confidence < 0:
            continue  # -1 marks a layout row, not a word
        lines.setdefault(tuple(cols[1:5]), []).append((cols[11].strip(), left, top, width, height, confidence))

    result = []
    for words in lines.values():
        left = min(w[1] for w in words)
        top = min(w[2] for w in words)
        right = max(w[1] + w[3] for w in words)
        bottom = max(w[2] + w[4] for w in words)
        result.append(OcrLine(" ".join(w[0] for w in words), (left, top, right - left, bottom - top),
                              sum(w[5] for w in words) / len(words)))
    return result


def version(command: str, timeout: float = 10.0) -> str | None:
    """'5.4.0.20240606', or None if the program cannot be run. Used by the health check."""
    try:
        completed = subprocess.run([command, "--version"], capture_output=True, timeout=timeout, check=False,
                                   creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return None
    first = (completed.stdout or completed.stderr).decode("utf-8", errors="replace").splitlines()
    return first[0].removeprefix("tesseract ").removeprefix("v").strip() if first else None


def languages(command: str, timeout: float = 10.0) -> set[str]:
    try:
        completed = subprocess.run([command, "--list-langs"], capture_output=True, timeout=timeout, check=False,
                                   creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return {line.strip() for line in completed.stdout.decode("utf-8", errors="replace").splitlines()[1:] if line.strip()}
