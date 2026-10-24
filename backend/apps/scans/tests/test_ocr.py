"""OCR in the application: intake, the worker, storage and health (FR-023, FR-027, NFR-032). Cycle 8.

Tests that run the real Tesseract are skipped where it is not installed.
"""

import os
import unittest

from django.test import override_settings
from django.urls import reverse

from apps.core import health
from apps.core.health import check_ocr
from apps.scans import worker
from apps.scans.models import Finding, Scan, ScannedFile
from tests.engine import builders
from tests.engine.detection_corpus import aadhaar

from .test_worker import WorkerTestBase

TESSERACT = os.environ.get("PRIVGUARD_TESSERACT", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
needs_tesseract = unittest.skipUnless(os.path.isfile(TESSERACT), "Tesseract is not installed")
OCR_ON = {"OCR_ENABLED": True, "TESSERACT_CMD": TESSERACT}
FS, E = ScannedFile.Status, ScannedFile.Extraction


class IntakeTests(WorkerTestBase):
    def test_with_ocr_off_images_are_unsupported_and_say_why(self):
        self.make_scan(files=(("photo.png", builders.png_header_only(10, 10)),))
        record = ScannedFile.objects.get()
        self.assertEqual(record.processing_status, FS.UNSUPPORTED)
        self.assertEqual(record.error_summary, "Text in images needs OCR, which is turned off on this server.")
        self.assertNotIn("png", self.client.get(reverse("scan-limits")).data["supported_extensions"])

    @needs_tesseract
    def test_with_ocr_on_images_are_accepted(self):
        with self.settings(**OCR_ON):
            scan = self.make_scan(files=(("photo.png", builders.png_header_only(10, 10)),
                                         ("scan.jpg", builders.jpeg_header_only(10, 10))))
            self.assertIn("png", self.client.get(reverse("scan-limits")).data["supported_extensions"])
        types = dict(ScannedFile.objects.values_list("file_name", "file_type"))
        self.assertEqual(types, {"photo.png": "png", "scan.jpg": "jpeg"})
        self.assertEqual(set(ScannedFile.objects.values_list("processing_status", flat=True)), {FS.PENDING})
        self.assertEqual(scan.configuration["intake_version"], 3)

    def test_a_missing_tesseract_counts_as_ocr_off(self):
        with self.settings(OCR_ENABLED=True, TESSERACT_CMD=r"C:\no\such\tesseract.exe"):
            self.make_scan(files=(("photo.png", builders.png_header_only(10, 10)),))
        self.assertEqual(ScannedFile.objects.get().processing_status, FS.UNSUPPORTED)


@needs_tesseract
class WorkerOcrTests(WorkerTestBase):
    def setUp(self):
        super().setUp()  # pins OCR off, so the developer's .env never decides a test...
        on = override_settings(**OCR_ON)  # ...and these tests switch it on explicitly
        on.enable()
        self.addCleanup(on.disable)

    def test_an_image_and_a_scanned_pdf_are_searched_and_stored_masked(self):
        number = aadhaar("23456789012")
        scan = self.queued([
            ("id-card.png", builders.png_bytes(f"Aadhaar: {number}")),
            ("scan.pdf", builders.scanned_pdf_bytes(["PAN: ABCPE1234F"])),
        ])
        self.claim_and_process()
        scan.refresh_from_db()
        self.assertEqual(scan.status, Scan.Status.COMPLETED)
        findings = {f.subcategory: f for f in Finding.objects.filter(scan=scan)}
        self.assertEqual(set(findings), {"aadhaar_number", "pan_number"})
        card = findings["aadhaar_number"]
        self.assertEqual((card.masked_value, card.source_location["kind"]), ("XXXX XXXX 0124", "ocr"))
        self.assertIn("ocr_box", card.source_location)
        self.assertIn("Read by OCR", card.description)
        self.assertEqual(findings["pan_number"].source_location["page"], 1)
        for row in Finding.objects.all():  # FR-115: masked only
            self.assertNotIn(number, str(vars(row)))

    def test_the_real_isolated_child_runs_tesseract(self):
        scan = self.queued([("id-card.png", builders.png_bytes("PAN: ABCPE1234F"))])
        worker.run_worker(once=True, log=lambda message: None)
        self.assertEqual(Scan.objects.get(pk=scan.pk).status, Scan.Status.COMPLETED)
        self.assertEqual(Finding.objects.get(scan=scan).subcategory, "pan_number")


class HealthTests(unittest.TestCase):
    def setUp(self):
        health._ocr_cache.clear()
        self.addCleanup(health._ocr_cache.clear)

    def test_disabled(self):
        with override_settings(OCR_ENABLED=False):
            self.assertEqual(check_ocr()[0], "disabled")

    def test_enabled_but_missing(self):
        with override_settings(OCR_ENABLED=True, TESSERACT_CMD=r"C:\no\such\tesseract.exe"):
            self.assertEqual(check_ocr(), ("error", "OCR is enabled, but TESSERACT_CMD does not point to tesseract.exe"))

    @needs_tesseract
    def test_enabled_and_working(self):
        with override_settings(**OCR_ON, OCR_LANGUAGES="eng"):
            status, detail = check_ocr()
        self.assertEqual(status, "ok")
        self.assertRegex(detail, r"^Tesseract \d+\.\d+.* \(eng\)$")

    @needs_tesseract
    def test_missing_language_data_is_named(self):
        with override_settings(**OCR_ON, OCR_LANGUAGES="eng+xyz"):
            self.assertEqual(check_ocr()[0], "error")
            self.assertIn("missing language data: xyz", check_ocr()[1])
