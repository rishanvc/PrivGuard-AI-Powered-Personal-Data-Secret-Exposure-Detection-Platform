"""Secrets and credentials (FR-046 to FR-055). Runs WITHOUT Django.

Every credential-shaped string here is assembled at runtime (secret_fixtures.py):
this file contains none.
"""

import ast
import base64
import re
import unittest
from pathlib import Path

from privguard_engine.detectors import (
    CATEGORY_OF, CONTEXT, ENTROPY, PATTERN, TYPE_LABELS, VALIDATED, DetectionConfig, FindingCollector, detect_segment,
)
from privguard_engine.detectors.masking import sanitise_preview
from privguard_engine.extractors.base import Segment

from . import secret_fixtures as s

BACKEND = Path(__file__).resolve().parents[2]
DETECTORS_DIR = BACKEND / "privguard_engine" / "detectors"


def detections(text, file_type="text", **location):
    return detect_segment(text, location, DetectionConfig(file_type=file_type))


def found(text, file_type="text", **location):
    return [(d.type, d.value) for d in detections(text, file_type, **location)]


def only(text, file_type="text", **location):
    result = detections(text, file_type, **location)
    assert len(result) == 1, result
    return result[0]


def finding(text, file_type="text", **location):
    collector = FindingCollector(DetectionConfig(file_type=file_type))
    collector(Segment(text, location))
    result, = collector.findings()
    return result


class RuleTests(unittest.TestCase):
    def test_a_known_format_is_a_pattern_match(self):
        token = s.github_token()
        detection = only(f"Use {token} for the deploy job")
        self.assertEqual((detection.type, detection.method, detection.confidence), ("api_token", PATTERN, 0.95))
        self.assertIn("Never checked against the service", detection.explanation)  # FR-055, said out loud

    def test_documentation_and_test_mode_keys_are_marked_as_such(self):
        self.assertEqual(only(f"key={s.aws_documentation_key_id()}", "env").type, "test_api_token")
        self.assertEqual(only(f"key={s.stripe_test_key()}", "env").type, "test_api_token")

    def test_a_known_token_wins_over_the_setting_that_holds_it(self):
        token = s.github_token()
        self.assertEqual(found(f"GITHUB_TOKEN={token}", "env"), [("api_token", token)])  # one finding, not two

    def test_a_jwt_is_validated_by_decoding_it(self):
        detection = only(f"Authorization: Bearer {s.jwt()}")
        self.assertEqual((detection.type, detection.method), ("jwt", VALIDATED))
        self.assertIn("HS256", detection.explanation)
        carrying = only(f"session={s.jwt({'sub': '42', 'email': 'synthetic'})}")
        self.assertIn("personal data (email)", carrying.explanation)  # the claim's NAME, never its value

    def test_basic_authentication_decodes_to_a_password(self):
        header = base64.b64encode(s.join("svc:", s.password()).encode()).decode()
        detection = only(f"Authorization: Basic {header}")
        self.assertEqual((detection.type, detection.method), ("password", VALIDATED))

    def test_the_same_line_means_different_things_in_different_files(self):
        self.assertEqual(found("password = get_password()", "code"), [])  # an expression
        self.assertEqual(found("password=get_password", "env")[0][0], "password")  # a value
        quoted = s.rand(16)
        self.assertEqual(found(f'password = "{quoted}"', "code"), [("password", quoted)])  # a string literal

    def test_in_prose_only_a_password_shaped_value_counts(self):
        self.assertEqual(found("Password: reset"), [])
        spoken = s.password()
        self.assertEqual(found(f"Password: {spoken}"), [("password", spoken)])

    def test_a_column_headed_password(self):
        value = s.rand(12)
        self.assertEqual(found(value, "xlsx", sheet="Users", cell="C2", header="Password"), [("password", value)])

    def test_placeholders_are_never_secrets(self):
        for placeholder in ("changeme", "change-me", "${DB_PASSWORD}", "$DB_PASSWORD", "%DB_PASSWORD%",
                            "<your-password>", "{{ db_password }}", "xxxxxxxx", "********", "your_password_here",
                            "replace-me-please", "ENC(AbCdEf123)", "/run/secrets/db_password", "example-password"):
            with self.subTest(placeholder=placeholder):
                self.assertEqual(found(f"DB_PASSWORD={placeholder}", "env"), [])

    def test_keys_that_describe_a_secret_do_not_hold_one(self):
        for line in ("TOKEN_EXPIRY_SECONDS=3600", "PASSWORD_MIN_LENGTH=12", "SECRET_NAME=db-credentials",
                     "API_KEY_ID=prod-key-7", "TOKEN_URL=https://auth.synthetic.net/token"):
            with self.subTest(line=line):
                self.assertEqual(found(line, "env"), [])

    def test_entropy_is_weak_evidence(self):
        value = s.mixed(40)
        detection = only(f'  "x_request_signer": "{value}",', "json")
        self.assertEqual((detection.type, detection.method, detection.confidence), ("high_entropy_secret", ENTROPY, 0.4))
        self.assertEqual(found(f'  "sha256": "{value}",', "json"), [])  # random by design
        self.assertEqual(found(f"note: {value}", "text"), [])  # entropy only where a value is unambiguous

    def test_secrets_in_settings_are_context_matches(self):
        self.assertEqual(only(f"DB_PASSWORD={s.rand(16)}", "env").method, CONTEXT)

    def test_privguards_own_env_example_has_nothing_to_find(self):
        lines = (BACKEND / ".env.example").read_text(encoding="utf-8").splitlines()
        self.assertGreater(len(lines), 20)
        for number, line in enumerate(lines, 1):
            with self.subTest(line=number):
                self.assertEqual(found(line, "env", line=number), [])


class MaskingTests(unittest.TestCase):
    def test_masks_say_what_was_found_never_its_content(self):
        password = s.rand(16)
        cases = {
            f"GITHUB_TOKEN={s.github_token()}": "ghp_****",
            f"DATABASE_URL=postgres://app:{password}@db.internal.example:5432/app":
                "postgres://****:****@db.internal.example:5432",
            s.pem_begin(): "-----BEGIN RSA PRIVATE KEY----- (contents not shown)",
            f"DB_PASSWORD={password}": "********",
            f"Authorization: Bearer {s.jwt()}": "eyJ****.eyJ****.****",
            f"aws_access_key_id = {s.aws_key_id()}": "AKIA****",
        }
        for text, expected in cases.items():
            with self.subTest(expected=expected):
                result = finding(text, "env")
                self.assertEqual(result.masked_value, expected)
                self.assertNotIn(password, result.context)

    def test_a_private_key_detection_spans_its_whole_block(self):
        # Checked on its own: the preview sanitiser below would ALSO hide a body,
        # so a test of previews alone could not tell the two safeguards apart.
        block = "\n".join([s.pem_begin(), s.pem_body(), s.pem_end()])
        detection = only(f"Key: {block} (rotated yearly)", "docx")
        self.assertEqual(detection.value, block)

    def test_a_private_key_body_never_reaches_a_preview(self):
        body = s.pem_body()
        text = "\n".join(["Key for the build server:", s.pem_begin(), body, s.pem_end(), "Ask the platform team."])
        result = finding(text, "docx", part="body", paragraph=4)
        self.assertNotIn(body[:12], result.context)
        self.assertIn("(contents not shown)", result.context)

    def test_previews_hide_random_tokens_nobody_claimed(self):
        token = s.mixed(30)
        self.assertEqual(sanitise_preview(f"ref {token} ok"), f"ref {'*' * 30} ok")
        for readable in ("report_2026_final_version_3", "550e8400-e29b-41d4-a716-446655440000"):
            with self.subTest(readable=readable):
                # Not random-looking: only Cycle 5's rule for runs of 4+ digits applies (D-032).
                digits_only = re.sub(r"\d{4,}", lambda m: "*" * len(m.group()), readable)
                self.assertEqual(sanitise_preview(readable), digits_only)


class CategoryTests(unittest.TestCase):
    def test_every_type_has_a_label_and_a_category(self):
        self.assertEqual(set(CATEGORY_OF), set(TYPE_LABELS))

    def test_secret_findings_are_in_the_secret_category(self):
        self.assertEqual(finding(f"GITHUB_TOKEN={s.github_token()}", "env").category, "secret")


class NeverVerifyTests(unittest.TestCase):
    """FR-055: PrivGuard never tests a credential against its service - so the
    detection code must not even be ABLE to reach the network."""

    NETWORK = {"socket", "ssl", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib", "smtplib", "telnetlib"}

    def test_no_detector_imports_a_network_library(self):
        for path in sorted(DETECTORS_DIR.glob("*.py")):
            imported = set()
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    imported |= {alias.name.split(".")[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    imported.add(node.module.split(".")[0])
            with self.subTest(module=path.name):
                self.assertFalse(imported & self.NETWORK, f"{path.name} imports {imported & self.NETWORK}")


if __name__ == "__main__":
    unittest.main()
