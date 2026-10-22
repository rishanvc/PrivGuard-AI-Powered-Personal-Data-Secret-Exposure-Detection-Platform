"""Scan creation and file intake over the API (Cycle 3).

FR-008/009/010/012/013/015/017/019, NFR-009/010/012/028.
"""

import hashlib
import re
from unittest import mock

from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.middleware import RequestSizeLimitMiddleware
from apps.scans.models import Scan, ScannedFile

from .base import DOCX, EXE, MB, PDF, ScanTestBase, zip_with


class MixedUploadTests(ScanTestBase):
    FILES = [
        ("report.pdf", PDF),
        ("letter.docx", DOCX),
        ("notes.txt", b"synthetic meeting notes\n"),
        ("invoice.pdf", EXE),                         # an executable pretending to be a PDF
        ("backup.zip", zip_with("inner.txt")),
        ("empty.txt", b""),
        ("copy.txt", b"synthetic meeting notes\n"),   # same bytes as notes.txt
    ]

    def test_every_file_gets_a_status_and_a_reason(self):
        r = self.upload(self.FILES)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["status"], "draft")
        self.assertEqual(r.data["total_files"], 7)

        rows = self.inventory(r.data["id"])
        self.assertEqual(
            {name: row["status"] for name, row in rows.items()},
            {
                "report.pdf": "pending", "letter.docx": "pending", "notes.txt": "pending",
                "invoice.pdf": "rejected", "backup.zip": "unsupported",
                "empty.txt": "skipped", "copy.txt": "skipped",
            },
        )
        self.assertIn("Windows executable", rows["invoice.pdf"]["reason"])
        self.assertIn("Archives are not supported", rows["backup.zip"]["reason"])
        self.assertEqual(rows["copy.txt"]["duplicate_of_path"], "notes.txt")
        self.assertEqual(rows["report.pdf"]["reason"], "")

    def test_counts_and_available_actions(self):
        r = self.upload(self.FILES)
        counts = r.data["file_counts"]
        self.assertEqual(
            (counts["pending"], counts["rejected"], counts["unsupported"], counts["skipped"]),
            (3, 1, 1, 2),
        )
        self.assertEqual(r.data["actions"], {"start": True, "cancel": False, "delete": True})

    def test_only_accepted_files_are_stored_and_under_random_names(self):
        r = self.upload(self.FILES)
        # Rejected, unsupported, empty and duplicate files are never kept.
        self.assertEqual(len(self.stored_files()), 3)

        pattern = re.compile(rf"^{self.alice.pk}/{r.data['id']}/[0-9a-f]{{32}}$")
        accepted = ScannedFile.objects.filter(scan_id=r.data["id"], processing_status="pending")
        for record in accepted:
            self.assertRegex(record.stored_file.name, pattern)
            with record.stored_file.open("rb") as stored:
                self.assertEqual(hashlib.sha256(stored.read()).hexdigest(), record.file_hash)

    def test_stored_files_have_no_url(self):
        self.upload([("notes.txt", b"synthetic\n")])
        with self.assertRaises(ValueError):
            ScannedFile.objects.get().stored_file.url

    def test_api_never_exposes_storage_location_or_hash(self):
        r = self.upload([("notes.txt", b"synthetic\n")])
        row = self.inventory(r.data["id"])["notes.txt"]
        self.assertNotIn("stored_file", row)
        self.assertNotIn("file_hash", row)


class LimitTests(ScanTestBase):
    @override_settings(MAX_UPLOAD_SIZE_MB=1)
    def test_oversized_file_is_rejected_and_not_stored_while_others_continue(self):
        r = self.upload([("big.txt", b"a" * (MB + 1)), ("small.txt", b"synthetic\n")])
        self.assertEqual(r.status_code, 201)
        rows = self.inventory(r.data["id"])
        self.assertEqual(rows["big.txt"]["status"], "rejected")
        self.assertIn("1 MB", rows["big.txt"]["reason"])
        self.assertEqual(rows["small.txt"]["status"], "pending")
        self.assertEqual(len(self.stored_files()), 1)

    @override_settings(MAX_TOTAL_SCAN_SIZE_MB=1)
    def test_oversized_request_is_refused_before_parsing(self):
        with self.assertLogs("apps.core.middleware", "WARNING"):
            r = self.upload([("huge.txt", b"a" * (2 * MB))])
        self.assertEqual(r.status_code, 413)
        self.assertIn("Upload too large", r.json()["detail"])
        self.assertEqual(Scan.objects.count(), 0)
        self.assertEqual(self.stored_files(), [])

    @override_settings(MAX_FILES_PER_SCAN=3, DATA_UPLOAD_MAX_NUMBER_FILES=3)
    def test_too_many_files_is_a_clear_json_error(self):
        files = [(f"f{i}.txt", f"synthetic {i}\n".encode()) for i in range(4)]
        with self.assertLogs("apps.core.middleware", "WARNING"):
            r = self.upload(files)
        self.assertEqual(r.status_code, 400)
        self.assertIn("Too many files", r.json()["detail"])
        self.assertEqual(Scan.objects.count(), 0)

    @override_settings(MAX_FILES_PER_SCAN=2, DATA_UPLOAD_MAX_NUMBER_FILES=10)
    def test_serializer_also_enforces_the_file_count(self):
        # Defence in depth: if the two settings ever drift apart, the
        # serializer still refuses.
        files = [(f"f{i}.txt", f"synthetic {i}\n".encode()) for i in range(3)]
        r = self.upload(files)
        self.assertEqual(r.status_code, 400)
        self.assertIn("files", r.data)


class FolderUploadTests(ScanTestBase):
    def test_relative_paths_are_recorded_and_traversal_rejected(self):
        r = self.upload(
            [("app.py", b"print('synthetic')\n"), (".env", b"DEBUG=false\n"), ("evil.txt", b"synthetic\n")],
            scan_type="folder",
            paths=["project/src/app.py", "project/.env", "project/../../evil.txt"],
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["name"], "project")  # default name: the folder's name

        rows = self.inventory(r.data["id"], key="relative_path")
        self.assertEqual(rows["project/src/app.py"]["status"], "pending")
        self.assertEqual(rows["project/src/app.py"]["file_type"], "code")
        self.assertEqual(rows["project/.env"]["file_type"], "env")
        self.assertEqual(rows["evil.txt"]["status"], "rejected")
        self.assertIn("traversal", rows["evil.txt"]["reason"])

    def test_bidi_disguised_traversal_in_a_path_is_rejected(self):
        # Paths arrive as plain form fields, which Django does NOT sanitise
        # (unlike multipart filenames) - so our own check is what stops this.
        r = self.upload([("x.txt", b"synthetic\n")], scan_type="folder", paths=["project/.\u202e./x.txt"])
        row = next(iter(self.inventory(r.data["id"]).values()))
        self.assertEqual(row["status"], "rejected")
        self.assertIn("traversal", row["reason"])

    def test_folder_upload_needs_one_path_per_file(self):
        r = self.upload([("a.txt", b"x"), ("b.txt", b"y")], scan_type="folder", paths=["p/a.txt"])
        self.assertEqual(r.status_code, 400)
        self.assertIn("paths", r.data)

    def test_paths_are_refused_for_plain_file_uploads(self):
        r = self.upload([("a.txt", b"x")], paths=["p/a.txt"])
        self.assertEqual(r.status_code, 400)


class NameSafetyTests(ScanTestBase):
    def test_bidi_spoofed_name_is_shown_with_its_real_extension(self):
        r = self.upload([("invoice\u202efdp.exe", EXE)])
        row = next(iter(self.inventory(r.data["id"]).values()))
        self.assertEqual(row["file_name"], "invoicefdp.exe")
        self.assertEqual(row["status"], "unsupported")


class FailureCleanupTests(ScanTestBase):
    def test_failure_midway_leaves_no_files_and_no_records(self):
        from apps.scans import services

        real_record = services._record
        calls = {"n": 0}

        def fail_on_second_file(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("simulated failure while saving the second file")
            return real_record(*args, **kwargs)

        with mock.patch("apps.scans.services._record", side_effect=fail_on_second_file), \
                self.settings(DEBUG_PROPAGATE_EXCEPTIONS=True), \
                self.assertRaises(RuntimeError):
            self.upload([("a.txt", b"synthetic a\n"), ("b.txt", b"synthetic b\n")])

        self.assertEqual(Scan.objects.count(), 0)    # the transaction rolled back the rows...
        self.assertEqual(self.stored_files(), [])    # ...and both written files were removed


class AccessTests(ScanTestBase):
    def test_anonymous_requests_are_refused(self):
        anonymous = APIClient()
        self.assertEqual(anonymous.get(reverse("scan-list")).status_code, 403)
        self.assertEqual(anonymous.get(reverse("scan-limits")).status_code, 403)
        self.assertEqual(anonymous.get(reverse("dashboard")).status_code, 403)
        self.assertEqual(self.upload([("a.txt", b"x")], client=anonymous).status_code, 403)
        self.assertEqual(Scan.objects.count(), 0)

    def test_upload_without_csrf_token_is_refused(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.alice)
        r = self.upload([("a.txt", b"x")], client=client)
        self.assertEqual(r.status_code, 403)
        self.assertIn("CSRF", r.data["detail"])
        self.assertEqual(Scan.objects.count(), 0)

    def test_limits_endpoint_reports_the_real_settings(self):
        r = self.client.get(reverse("scan-limits"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["max_file_mb"], settings.MAX_UPLOAD_SIZE_MB)
        self.assertEqual(r.data["max_total_mb"], settings.MAX_TOTAL_SCAN_SIZE_MB)
        self.assertEqual(r.data["max_files"], settings.MAX_FILES_PER_SCAN)
        self.assertIn("pdf", r.data["supported_extensions"])
        self.assertNotIn("png", r.data["supported_extensions"])


class RequestSizeLimitMiddlewareTests(SimpleTestCase):
    """The gate on its own: no database, no view, no body ever read."""

    def setUp(self):
        self.middleware = RequestSizeLimitMiddleware(lambda request: HttpResponse("reached the view"))
        self.factory = RequestFactory()

    def post(self, **extra):
        return self.factory.post("/api/scans/", data=b"x", content_type="application/octet-stream", **extra)

    def test_small_request_passes_through(self):
        self.assertEqual(self.middleware(self.post()).content, b"reached the view")

    @override_settings(MAX_TOTAL_SCAN_SIZE_MB=1)
    def test_declared_size_over_the_limit_is_refused(self):
        with self.assertLogs("apps.core.middleware", "WARNING"):
            r = self.middleware(self.post(CONTENT_LENGTH=str(5 * MB)))
        self.assertEqual(r.status_code, 413)

    def test_invalid_content_length_is_refused(self):
        self.assertEqual(self.middleware(self.post(CONTENT_LENGTH="abc")).status_code, 400)
