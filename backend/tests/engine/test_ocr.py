"""OCR: image headers, Tesseract's output, images and scanned PDFs (FR-023, FR-027). Runs WITHOUT Django.

Tests marked @needs_tesseract run the real program and are skipped where it is
not installed. Every image is synthetic, drawn by tests/engine/builders.py.
"""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from privguard_engine.detectors import DetectionConfig
from privguard_engine.extractors import ExtractionStatus, Limits, extract_file
from privguard_engine.extractors import ocr as ocr_module
from privguard_engine.extractors import pdf as pdf_module
from privguard_engine.extractors.base import ExtractionError, NotSupported, Report
from privguard_engine.extractors.image import note_confidence
from privguard_engine.extractors.ocr import OcrConfig, OcrLine, check_pixels, image_size, parse_tsv, write_pgm
from privguard_engine.isolation import Job, perform

from . import builders as b
from .detection_corpus import aadhaar

TESSERACT = os.environ.get("PRIVGUARD_TESSERACT", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
needs_tesseract = unittest.skipUnless(os.path.isfile(TESSERACT), "Tesseract is not installed")
MAIL = "mailhost-synthetic.net"


class Folder(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="privguard-ocr-")
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.config = OcrConfig(command=TESSERACT, temp_dir=self.folder)

    def stored(self, content: bytes, name: str = "stored") -> str:
        path = os.path.join(self.folder, name)  # extensionless, like a real upload
        with open(path, "wb") as handle:
            handle.write(content)
        return path


class HeaderTests(Folder):
    def test_sizes_come_from_the_header_alone(self):
        self.assertEqual(image_size(self.stored(b.png_header_only(1200, 800))), (1200, 800))
        self.assertEqual(image_size(self.stored(b.jpeg_header_only(4000, 3000))), (4000, 3000))

    def test_damaged_or_foreign_files_are_refused(self):
        for content in (b"not an image at all", b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, b"\xff\xd8\xff\xe0\x00"):
            with self.subTest(content=content[:12]), self.assertRaises(ExtractionError):
                image_size(self.stored(content))

    def test_a_decompression_bomb_is_refused_before_any_pixel_is_decoded(self):
        width, height = image_size(self.stored(b.png_header_only(50_000, 50_000)))  # 2.5 billion pixels claimed
        with self.assertRaises(NotSupported):
            check_pixels(width, height, self.config)
        with self.assertRaises(ExtractionError):
            check_pixels(0, 10, self.config)


class OutputTests(unittest.TestCase):
    def test_tesseract_tsv_becomes_lines_in_reading_order(self):
        tsv = "\n".join([
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "4\t1\t1\t1\t1\t0\t10\t10\t200\t20\t-1\t",               # a layout row, not a word
            "5\t1\t1\t1\t1\t1\t10\t10\t60\t20\t95.5\tName:",
            "5\t1\t1\t1\t1\t2\t80\t12\t90\t22\t90.5\tAsha",
            "5\t1\t1\t1\t2\t1\t10\t50\t70\t20\t-1\t",                 # no text: skipped
            "5\t1\t1\t1\t2\t2\t10\t50\t70\t20\t88.0\tPAN:",
            "5\t1\t1\t1\t2\t3\tx\t50\t70\t20\t88.0\tbroken",          # unreadable numbers: skipped
        ])
        lines = parse_tsv(tsv)
        self.assertEqual([line.text for line in lines], ["Name: Asha", "PAN:"])
        self.assertEqual(lines[0].box, (10, 10, 160, 24))
        self.assertAlmostEqual(lines[0].confidence, 93.0)

    def test_pgm_rows_ignore_padding(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "page.pgm")
        write_pgm(path, 2, 2, 4, b"\x01\x02PP\x03\x04PP")  # stride 4: two padding bytes per row
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), b"P5\n2 2\n255\n\x01\x02\x03\x04")

    def test_low_confidence_is_reported(self):
        report = Report()
        note_confidence([OcrLine("blurry", (0, 0, 1, 1), 41.0)], report, "this image")
        self.assertIn("average 41 of 100", report.notes[0])


class OcrOffTests(Folder):
    def test_without_ocr_images_and_scans_are_reported_not_read(self):
        image = extract_file(self.stored(b.png_header_only(10, 10), "image"), "png")
        self.assertEqual((image.status, image.reason), (ExtractionStatus.NOT_SUPPORTED,
                                                       "Text in images needs OCR, which is turned off on this server."))
        scan = extract_file(self.stored(b.scanned_pdf_bytes(["synthetic"]), "scan"), "pdf")
        self.assertEqual(scan.status, ExtractionStatus.NOT_SUPPORTED)
        self.assertIn("needs OCR, which is turned off", scan.reason)


@needs_tesseract
class ImageTests(Folder):
    def test_an_image_is_read_line_by_line_with_positions(self):
        segments = []
        result = extract_file(self.stored(b.png_bytes(f"Email: asha.example@{MAIL}\nPAN: ABCPE1234F")), "png",
                              limits=Limits(ocr=self.config), sink=segments.append)
        self.assertEqual(result.status, ExtractionStatus.SUCCEEDED)
        self.assertEqual([s.text for s in segments], [f"Email: asha.example@{MAIL}", "PAN: ABCPE1234F"])
        self.assertEqual(segments[0].location["kind"], "ocr")
        self.assertEqual(len(segments[0].location["ocr_box"].split(",")), 4)  # left, top, width, height
        self.assertEqual(result.stats["ocr_lines"], 2)

    def test_findings_in_an_image_say_they_came_from_ocr(self):
        path = self.stored(b.png_bytes(f"Aadhaar: {aadhaar('23456789012')}"))
        reply = perform(Job(path, "png", Limits(ocr=self.config), DetectionConfig()))
        finding, = reply.findings
        self.assertEqual((finding.type, finding.masked_value), ("aadhaar_number", "XXXX XXXX 0124"))
        self.assertIn("Read by OCR", finding.explanation)
        self.assertEqual(finding.location["kind"], "ocr")

    def test_a_bomb_never_reaches_tesseract(self):
        path = self.stored(b.png_header_only(50_000, 50_000))
        with mock.patch.object(ocr_module.subprocess, "run", side_effect=AssertionError("Tesseract must not run")):
            result = extract_file(path, "png", limits=Limits(ocr=self.config))
        self.assertEqual(result.status, ExtractionStatus.NOT_SUPPORTED)
        self.assertIn("too large to read safely", result.reason)


@needs_tesseract
class ScannedPdfTests(Folder):
    def test_scanned_pages_are_read_and_temporary_images_removed(self):
        segments = []
        path = self.stored(b.scanned_pdf_bytes([f"Aadhaar: {aadhaar('23456789012')}", "PAN: ABCPE1234F"]))
        result = extract_file(path, "pdf", limits=Limits(ocr=self.config), sink=segments.append)
        self.assertEqual(result.status, ExtractionStatus.SUCCEEDED)
        self.assertEqual([(s.location["page"], s.text) for s in segments],
                         [(1, f"Aadhaar: {aadhaar('23456789012')}"), (2, "PAN: ABCPE1234F")])
        self.assertEqual(result.stats["ocr_pages"], 2)
        self.assertEqual([f for f in os.listdir(self.folder) if f.startswith("ocr-")], [])  # FR-030

    def test_text_pages_are_read_directly_and_only_scanned_ones_by_ocr(self):
        mixed = b.pdf_bytes(["Typed page: PAN: ABCPE1234F", ""])  # page 2 has no text...
        # Spy where the PDF extractor LOOKS: it imported run_tesseract by name, so a spy
        # on the ocr module would count nothing - and "at most once" would pass at zero.
        with mock.patch.object(pdf_module, "run_tesseract", wraps=ocr_module.run_tesseract) as spy:
            # ...and it is blank: OCR runs once, for page 2 only, and finds nothing there.
            result = extract_file(self.stored(mixed), "pdf", limits=Limits(ocr=self.config))
        self.assertEqual(result.status, ExtractionStatus.SUCCEEDED)
        self.assertEqual(spy.call_count, 1)
        self.assertIn("OCR found no text on the scanned pages.", result.notes)

    def test_the_page_limit_is_reported(self):
        path = self.stored(b.scanned_pdf_bytes(["page one", "page two"]))
        config = OcrConfig(command=TESSERACT, temp_dir=self.folder, max_pages=1)
        result = extract_file(path, "pdf", limits=Limits(ocr=config))
        self.assertEqual(result.status, ExtractionStatus.PARTIAL)
        self.assertIn("OCR read only the first 1 of 2 scanned pages", result.reason)

    def test_running_out_of_time_fails_a_fully_scanned_file(self):
        path = self.stored(b.scanned_pdf_bytes(["page one"]))
        result = extract_file(path, "pdf", limits=Limits(ocr=OcrConfig(command=TESSERACT, temp_dir=self.folder,
                                                                         time_budget=0.0)))
        self.assertEqual(result.status, ExtractionStatus.FAILED)  # nothing at all was read: not "partly"
        self.assertIn("time allowed", result.reason)
        self.assertEqual([f for f in os.listdir(self.folder) if f.startswith("ocr-")], [])


if __name__ == "__main__":
    unittest.main()
