"""The committed sample folder produces exactly what samples/README.md documents.

Keeps the README honest: if intake rules change, this fails until the
documentation is updated to match.
"""

from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.scans import services
from apps.scans.models import Scan

from .base import ScanTestBase

SAMPLES = Path(settings.BASE_DIR).parent / "samples" / "intake-demo"

EXPECTED = {
    "intake-demo/empty.txt": "skipped",
    "intake-demo/report.pdf": "pending",
    "intake-demo/letter.docx": "pending",
    "intake-demo/invoice.pdf": "rejected",
    "intake-demo/photo.png": "unsupported",
    "intake-demo/backup.zip": "unsupported",
    "intake-demo/src/app.py": "pending",
    "intake-demo/config/settings.yaml": "pending",
    "intake-demo/config/sample.env": "pending",
}
DUPLICATE_PAIR = ("intake-demo/notes.txt", "intake-demo/notes_copy.txt")


class SampleFolderTests(ScanTestBase):
    def upload_sample_folder(self, order):
        if not SAMPLES.is_dir():
            self.skipTest("samples/intake-demo has not been generated")
        paths = order(p for p in SAMPLES.rglob("*") if p.is_file())
        files = [
            services.IncomingFile(
                SimpleUploadedFile(path.name, path.read_bytes()),
                path.relative_to(SAMPLES.parent).as_posix(),
            )
            for path in paths
        ]
        scan = services.create_scan(user=self.alice, name="", scan_type=Scan.ScanType.FOLDER, files=files)
        return {f.relative_path: f for f in scan.files.select_related("duplicate_of")}

    def check(self, records):
        statuses = {path: record.processing_status for path, record in records.items()}
        pair = {path: statuses.pop(path) for path in DUPLICATE_PAIR}
        self.assertEqual(statuses, EXPECTED)

        # Order-independent: one copy accepted, the other skipped as ITS duplicate.
        self.assertEqual(sorted(pair.values()), ["pending", "skipped"])
        skipped = next(path for path, status in pair.items() if status == "skipped")
        accepted = next(path for path, status in pair.items() if status == "pending")
        self.assertEqual(records[skipped].duplicate_of.relative_path, accepted)

    def test_matches_the_readme_in_alphabetical_order(self):
        self.check(self.upload_sample_folder(sorted))

    def test_matches_the_readme_in_reverse_order(self):
        self.check(self.upload_sample_folder(lambda paths: sorted(paths, reverse=True)))
