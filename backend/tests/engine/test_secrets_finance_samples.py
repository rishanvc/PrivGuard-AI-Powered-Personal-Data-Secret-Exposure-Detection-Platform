"""samples/make_secrets_finance_demo.py produces what samples/README.md says it does.

The files are never committed (D-038), so this test builds them in a temporary
folder from the generator itself, then runs the real intake, extraction,
detection and severity policy over them. Runs without Django.
"""

import importlib.util
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from privguard_engine.detectors import DetectionConfig
from privguard_engine.extractors import Limits
from privguard_engine.intake import Verdict, inspect_file
from privguard_engine.isolation import Job, perform
from privguard_engine.risk import assess

REPO = Path(__file__).resolve().parents[3]

EXPECTED = {
    "deploy.env": {"connection_string": 1, "api_token": 1, "cloud_credential": 2, "test_api_token": 1},
    "build-server.pem": {"private_key": 1},
    "settings.json": {"secret_assignment": 1, "jwt": 1, "high_entropy_secret": 1},
    "payments.csv": {"person_name": 2, "payment_card": 2, "card_security_code": 2, "upi_id": 2, "bank_account": 2,
                     "ifsc_code": 2},
    "bank-letter.docx": {"person_name": 2, "bank_account": 1, "ifsc_code": 1, "iban": 1, "swift_code": 1, "gstin": 1,
                         "transaction_id": 1, "test_payment_card": 1},
}


def load_generator():
    spec = importlib.util.spec_from_file_location("make_secrets_finance_demo",
                                                  REPO / "samples" / "make_secrets_finance_demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SecretsFinanceSampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = Path(tempfile.mkdtemp(prefix="privguard-demo-"))
        cls.addClassCleanup(shutil.rmtree, folder, True)
        cls.results = {}
        for name, content in load_generator().build().items():
            path = folder / name
            path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
            with path.open("rb") as stream:
                inspection = inspect_file(name, stream, path.stat().st_size, 25 * 1024 * 1024)
            assert inspection.verdict is Verdict.SUPPORTED, (name, inspection.reason)
            cls.results[name] = perform(Job(str(path), inspection.file_type, Limits(), DetectionConfig()))

    def test_each_file_finds_what_the_readme_says(self):
        for name, expected in EXPECTED.items():
            with self.subTest(file=name):
                self.assertEqual(self.results[name].detection["by_type"], expected)

    def test_severity_spread(self):
        levels = Counter(assess(f.type, f.confidence).level
                         for result in self.results.values() for f in result.findings)
        self.assertEqual(levels, {"critical": 5, "high": 10, "medium": 3, "low": 10, "informational": 2})

    def test_placeholders_in_the_env_file_are_not_reported(self):
        masked = [f.context for f in self.results["deploy.env"].findings]
        self.assertFalse(any("SMTP_PASSWORD" in context or "TOKEN_EXPIRY" in context for context in masked))
