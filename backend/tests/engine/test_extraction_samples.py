"""samples/extraction-demo/ produces what samples/README.md says it does.

Runs the real intake and extractors over the committed samples, without Django.
If an extractor changes behaviour, this fails until the README is updated.
"""

import unittest
from pathlib import Path

from privguard_engine.extractors import extract_file
from privguard_engine.intake import Verdict, inspect_file

REPO = Path(__file__).resolve().parents[3]
SAMPLES = REPO / "samples" / "extraction-demo"
README = REPO / "samples" / "README.md"

EXPECTED = {
    "staff.xlsx": "succeeded",
    "letter.docx": "succeeded",
    "deck.pptx": "succeeded",
    "report.pdf": "partial",
    "scanned.pdf": "not_supported",
    "customers.csv": "succeeded",
    "legacy-notes.txt": "succeeded",
    "windows-export-utf16.txt": "succeeded",
}


class ExtractionSampleTests(unittest.TestCase):
    def extract(self, name):
        path = SAMPLES / name
        if not path.is_file():
            self.skipTest("samples/extraction-demo has not been generated")
        with path.open("rb") as stream:
            inspection = inspect_file(name, stream, path.stat().st_size, 25 * 1024 * 1024)
        self.assertEqual(inspection.verdict, Verdict.SUPPORTED, inspection.reason)
        segments = []
        result = extract_file(str(path), inspection.file_type, sink=segments.append)
        return result, segments

    @staticmethod
    def find(segments, text):
        return next(s for s in segments if s.text == text)

    def test_every_sample_has_its_documented_status(self):
        readme = README.read_text(encoding="utf-8")
        for name, status in EXPECTED.items():
            with self.subTest(sample=name):
                self.assertIn(f"`{name}`", readme)
                result, _ = self.extract(name)
                self.assertEqual(result.status.value, status, result.reason)

    def test_the_highlights_the_readme_promises(self):
        _, staff = self.extract("staff.xlsx")
        self.assertTrue(self.find(staff, "Cara Example").location["hidden"])
        self.assertEqual(self.find(staff, "+44 20 7946 0001").location["header"], "Phone")
        self.assertTrue(any("intranet.example.com/reports" in s.text for s in staff))

        _, letter = self.extract("letter.docx")
        self.assertEqual(self.find(letter, "Your previous account was 00-11-22 12345678.").location["kind"], "deleted")
        self.assertTrue(any(s.location.get("kind") == "field code" and "customers/42" in s.text for s in letter))

        _, deck = self.extract("deck.pptx")
        note = next(s for s in deck if s.location.get("part") == "notes")
        self.assertEqual(note.location["slide"], 2)

        _, customers = self.extract("customers.csv")
        self.assertEqual(self.find(customers, "Ben Example").location["line"], 4)

        legacy, _ = self.extract("legacy-notes.txt")
        self.assertEqual(legacy.stats["encoding"], "windows-1252")
        utf16, _ = self.extract("windows-export-utf16.txt")
        self.assertEqual(utf16.stats["encoding"], "utf-16")

    def test_the_inspection_command_runs(self):
        import contextlib
        import io

        from privguard_engine.extractors.__main__ import main

        if not (SAMPLES / "letter.docx").is_file():
            self.skipTest("samples/extraction-demo has not been generated")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main([str(SAMPLES / "letter.docx"), "--max", "3"])
        self.assertEqual(exit_code, 0)
        self.assertIn("result: succeeded", output.getvalue())
        self.assertIn("more segments", output.getvalue())


if __name__ == "__main__":
    unittest.main()
