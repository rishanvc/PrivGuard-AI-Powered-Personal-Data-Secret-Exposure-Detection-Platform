"""No invisible or direction-changing characters in our own source code.

"Trojan Source" (CVE-2021-42574): a literal RIGHT-TO-LEFT OVERRIDE makes a
line DISPLAY differently from how it EXECUTES. Code that needs such a
character must write it as an escape such as "\\u202e", which is visible.

This guard exists because one slipped into a Cycle 3 test unnoticed.
Runs without Django.
"""

import shutil
import tempfile
import unittest
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

# Built from code points, so this file cannot contain the characters itself.
SUSPECT = frozenset(map(chr, (
    0x061C, 0x200B, 0x200C, 0x200D, 0x200E, 0x200F,
    0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
    0x2066, 0x2067, 0x2068, 0x2069, 0xFEFF,
)))
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".css", ".html", ".md", ".json", ".toml", ".yaml", ".yml"}
SKIP_DIRS = {".venv", "node_modules", "__pycache__", "var", "dist", ".git"}


def source_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in SOURCE_SUFFIXES and not SKIP_DIRS.intersection(path.parts):
            yield path


def find_invisible(paths) -> list[str]:
    problems = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # binary or deliberately non-UTF-8 sample data
        for number, line in enumerate(text.splitlines(), 1):
            for char in sorted(SUSPECT.intersection(line)):
                problems.append(f"{path}:{number}: U+{ord(char):04X} {unicodedata.name(char, '?')}")
    return problems


class SourceHygieneTests(unittest.TestCase):
    def test_repository_source_has_no_invisible_characters(self):
        roots = [REPO / "backend", REPO / "frontend" / "src", REPO / "samples", REPO / "docs"]
        files = [p for root in roots if root.is_dir() for p in source_files(root)]
        files += [p for p in REPO.glob("*.md")]
        self.assertGreater(len(files), 20, "the scan found suspiciously few files")
        self.assertEqual(find_invisible(files), [])

    def test_the_scanner_actually_catches_one(self):
        # Without this, a broken scanner would make the test above pass forever.
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        planted = folder / "planted.py"
        planted.write_text('name = "invoice' + chr(0x202E) + 'fdp.exe"\n', encoding="utf-8")
        self.assertEqual(len(find_invisible([planted])), 1)


if __name__ == "__main__":
    unittest.main()
