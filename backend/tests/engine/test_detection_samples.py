"""samples/detection-demo/ produces what samples/README.md says it does.

Runs the real intake, extraction and detection over the committed samples,
without Django. If a rule changes behaviour, this fails until the README is
updated.
"""

import unittest
from pathlib import Path

from privguard_engine.detectors import DetectionConfig
from privguard_engine.extractors import Limits
from privguard_engine.intake import Verdict, inspect_file
from privguard_engine.isolation import Job, perform

REPO = Path(__file__).resolve().parents[3]
SAMPLES = REPO / "samples" / "detection-demo"

EXPECTED = {
    "employees.csv": {"person_name": 3, "phone_number": 3, "email_address": 3, "date_of_birth": 3,
                      "aadhaar_number": 3, "pan_number": 3, "gender": 2, "blood_group": 2},
    "hr-letter.docx": {"person_name": 2, "employee_id": 1, "pan_number": 1, "date_of_birth": 1,
                       "postal_address": 1, "postal_code": 1, "phone_number": 1, "email_address": 1},
    "notes.txt": {"person_name": 1, "aadhaar_number": 1, "passport_number": 1, "religion_or_caste": 1},
    "lookalikes.txt": {},
}


class DetectionSampleTests(unittest.TestCase):
    def search(self, name):
        path = SAMPLES / name
        if not path.is_file():
            self.skipTest("samples/detection-demo has not been generated")
        with path.open("rb") as stream:
            inspection = inspect_file(name, stream, path.stat().st_size, 25 * 1024 * 1024)
        self.assertEqual(inspection.verdict, Verdict.SUPPORTED, inspection.reason)
        return perform(Job(str(path), inspection.file_type, Limits(), DetectionConfig()))

    def test_each_sample_finds_what_the_readme_says(self):
        for name, expected in EXPECTED.items():
            with self.subTest(file=name):
                self.assertEqual(self.search(name).detection["by_type"], expected)

    def test_the_name_in_prose_is_a_known_gap(self):
        names = [f.masked_value for f in self.search("notes.txt").findings if f.type == "person_name"]
        self.assertEqual(names, ["R*** E******"])  # "Ravi Example" is labelled; "Asha Example" in prose is not found

    def test_repeated_values_are_grouped(self):
        genders = [(f.masked_value, f.occurrences) for f in self.search("employees.csv").findings if f.type == "gender"]
        # Female twice, Male once. Both masks are identical: the mask reveals neither value.
        self.assertEqual(sorted(genders), [("****", 1), ("****", 2)])
