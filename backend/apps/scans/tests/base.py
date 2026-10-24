"""Shared fixtures for scan tests. Every file content here is synthetic."""

import io
import shutil
import tempfile
import zipfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.scans import services
from apps.scans.models import Scan

User = get_user_model()
MB = 1024 * 1024

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< >>\nendobj\ntrailer\n<< >>\n%%EOF\n"
EXE = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00" + b"\x00" * 48
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 13


def zip_with(*parts):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for part in parts:
            archive.writestr(part, "<synthetic/>")
    return buffer.getvalue()


DOCX = zip_with("[Content_Types].xml", "word/document.xml")


class ScanTestBase(APITestCase):
    """Uploads go to a throwaway folder - never the real backend/var/uploads."""

    def setUp(self):
        self.upload_root = Path(tempfile.mkdtemp(prefix="privguard-test-"))
        self.addCleanup(shutil.rmtree, self.upload_root, True)
        # OCR off unless a test turns it on: results must not depend on the developer's .env.
        override = override_settings(UPLOAD_ROOT=self.upload_root, OCR_ENABLED=False)
        override.enable()
        self.addCleanup(override.disable)

        # No passwords: hashing one costs ~0.3 s and these tests never log in
        # with a password - force_login creates the session directly.
        self.alice = User.objects.create(username="alice")
        self.bob = User.objects.create(username="bob")
        self.ada = User.objects.create(username="ada", role=User.Role.ADMIN)
        self.client.force_login(self.alice)

    # ---- helpers

    def upload(self, files, scan_type="files", paths=None, name="", client=None):
        data = {
            "scan_type": scan_type,
            "name": name,
            "files": [SimpleUploadedFile(file_name, content) for file_name, content in files],
        }
        if paths is not None:
            data["paths"] = paths
        return (client or self.client).post(reverse("scan-list"), data, format="multipart")

    def make_scan(self, user=None, files=(("notes.txt", b"synthetic notes\n"),)):
        """Create a scan through the service layer - faster than the API."""
        return services.create_scan(
            user=user or self.alice,
            name="",
            scan_type=Scan.ScanType.FILES,
            files=[services.IncomingFile(SimpleUploadedFile(n, c)) for n, c in files],
        )

    def inventory(self, scan_id, key="file_name"):
        r = self.client.get(reverse("scan-files", kwargs={"pk": scan_id}))
        self.assertEqual(r.status_code, 200)
        return {row[key]: row for row in r.data["results"]}

    def stored_files(self):
        return sorted(p for p in self.upload_root.rglob("*") if p.is_file())

    def scan_dir(self, scan):
        return self.upload_root / str(scan.user_id) / str(scan.pk)

    def url(self, name, scan):
        return reverse(name, kwargs={"pk": scan.pk})
