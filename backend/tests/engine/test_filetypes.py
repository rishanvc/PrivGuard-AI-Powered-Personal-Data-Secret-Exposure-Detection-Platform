"""Content-based file-type detection (FR-012, FR-013). Runs WITHOUT Django.

    cd backend
    .venv/Scripts/python.exe -m unittest discover -s tests/engine -t .

Every file below is synthetic and built in memory.
"""

import io
import unittest
import zipfile

from privguard_engine.intake import Verdict, inspect_file

MB = 1024 * 1024
LIMIT = 25 * MB

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< >>\nendobj\ntrailer\n<< >>\n%%EOF\n"
EXE = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00" + b"\x00" * 48
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 13


def zip_with(*parts: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for part in parts:
            archive.writestr(part, "<synthetic/>")
    return buffer.getvalue()


DOCX = zip_with("[Content_Types].xml", "word/document.xml")
XLSX = zip_with("[Content_Types].xml", "xl/workbook.xml")
PPTX = zip_with("[Content_Types].xml", "ppt/presentation.xml")
PLAIN_ZIP = zip_with("notes.txt")


def inspect(name, content, limit=LIMIT):
    stream = io.BytesIO(content)
    return inspect_file(name, stream, len(content), limit), stream


class SupportedFormatTests(unittest.TestCase):
    def test_supported_formats_are_accepted_with_their_kind(self):
        cases = [
            ("report.pdf", PDF, "pdf"),
            ("letter.docx", DOCX, "docx"),
            ("budget.xlsx", XLSX, "xlsx"),
            ("notes.txt", b"meeting notes\n", "text"),
            ("app.py", b"print('hello')\n", "code"),
            ("data.csv", b"name,city\nA,B\n", "csv"),
            ("settings.yaml", b"debug: true\n", "yaml"),
            ("config.json", b'{"a": 1}', "json"),
            ("server.pem", b"synthetic certificate placeholder\n", "key"),
        ]
        for name, content, kind in cases:
            with self.subTest(name=name):
                result, _ = inspect(name, content)
                self.assertEqual(result.verdict, Verdict.SUPPORTED, result.reason)
                self.assertEqual(result.file_type, kind)

    def test_pdf_header_may_follow_leading_bytes(self):
        result, _ = inspect("report.pdf", b"\r\n\r\n" + PDF)
        self.assertEqual(result.verdict, Verdict.SUPPORTED)

    def test_env_files_are_recognised_by_name(self):
        for name in (".env", ".env.local", ".env.production", "prod.env"):
            with self.subTest(name=name):
                result, _ = inspect(name, b"DEBUG=false\n")
                self.assertEqual(result.verdict, Verdict.SUPPORTED)
                self.assertEqual(result.file_type, "env")

    def test_extensionless_text_files_are_supported(self):
        for name in ("Dockerfile", "Makefile", "id_rsa", ".npmrc", ".gitconfig"):
            with self.subTest(name=name):
                result, _ = inspect(name, b"synthetic plain text\n")
                self.assertEqual(result.verdict, Verdict.SUPPORTED)
                self.assertEqual(result.file_type, "text")

    def test_utf16_text_with_bom_is_text_despite_nul_bytes(self):
        content = "synthetic notes".encode("utf-16")  # BOM, then NUL after every ASCII char
        self.assertIn(b"\x00", content)
        result, _ = inspect("notes.txt", content)
        self.assertEqual(result.verdict, Verdict.SUPPORTED)


class MismatchTests(unittest.TestCase):
    def test_executable_renamed_to_pdf_is_rejected(self):
        result, _ = inspect("invoice.pdf", EXE)
        self.assertEqual(result.verdict, Verdict.REJECTED)
        self.assertIn("Windows executable", result.reason)

    def test_pdf_renamed_to_docx_is_rejected(self):
        result, _ = inspect("letter.docx", PDF)
        self.assertEqual(result.verdict, Verdict.REJECTED)
        self.assertIn("looks like a PDF", result.reason)

    def test_plain_zip_renamed_to_docx_is_rejected(self):
        result, _ = inspect("letter.docx", PLAIN_ZIP)
        self.assertEqual(result.verdict, Verdict.REJECTED)
        self.assertIn("without the parts of a Word document", result.reason)

    def test_corrupt_office_file_is_rejected_not_crashed(self):
        result, _ = inspect("budget.xlsx", b"PK\x03\x04" + b"not really a zip" * 20)
        self.assertEqual(result.verdict, Verdict.REJECTED)
        self.assertIn("damaged", result.reason)

    def test_binary_content_in_text_file_is_rejected(self):
        result, _ = inspect("notes.txt", b"looks like text\x00but is not")
        self.assertEqual(result.verdict, Verdict.REJECTED)
        self.assertIn("binary data", result.reason)

    def test_pdf_named_txt_is_rejected_even_without_nul_bytes(self):
        self.assertNotIn(b"\x00", PDF)
        result, _ = inspect("notes.txt", PDF)
        self.assertEqual(result.verdict, Verdict.REJECTED)
        self.assertIn("looks like a PDF", result.reason)

    def test_extensionless_binary_is_unsupported_not_rejected(self):
        # No extension means no claim was made, so nothing was mislabelled.
        result, _ = inspect("tool", EXE)
        self.assertEqual(result.verdict, Verdict.UNSUPPORTED)


class UnsupportedTests(unittest.TestCase):
    def test_archives_are_unsupported_with_guidance(self):
        for name in ("backup.zip", "logs.tar.gz", "dump.7z"):
            with self.subTest(name=name):
                result, _ = inspect(name, PLAIN_ZIP)
                self.assertEqual(result.verdict, Verdict.UNSUPPORTED)
                self.assertIn("Archives are not supported", result.reason)

    def test_images_are_recognised_but_unsupported_until_ocr(self):
        for name, file_type in (("photo.png", "png"), ("scan.jpg", "jpeg"), ("scan.jpeg", "jpeg")):
            with self.subTest(name=name):
                result, _ = inspect(name, PNG)
                self.assertEqual(result.verdict, Verdict.UNSUPPORTED)
                self.assertEqual(result.file_type, file_type)
                self.assertIn("OCR", result.reason)

    def test_powerpoint_is_unsupported(self):
        result, _ = inspect("deck.pptx", PPTX)
        self.assertEqual(result.verdict, Verdict.UNSUPPORTED)

    def test_unknown_types_are_unsupported(self):
        for name in ("setup.exe", "movie.mp4", "library.dll"):
            with self.subTest(name=name):
                result, _ = inspect(name, EXE)
                self.assertEqual(result.verdict, Verdict.UNSUPPORTED)
                self.assertEqual(result.reason, "This file type is not supported.")


class SizeLimitTests(unittest.TestCase):
    def test_oversized_file_is_rejected_without_being_read(self):
        class MustNotBeRead(io.BytesIO):
            def read(self, *args):
                raise AssertionError("an oversized file must not be read")

            def seek(self, *args):
                raise AssertionError("an oversized file must not be touched")

        result = inspect_file("big.pdf", MustNotBeRead(), 30 * MB, LIMIT)
        self.assertEqual(result.verdict, Verdict.REJECTED)
        self.assertIn("25 MB", result.reason)

    def test_file_exactly_at_the_limit_is_allowed(self):
        result = inspect_file("report.pdf", io.BytesIO(PDF), LIMIT, LIMIT)
        self.assertEqual(result.verdict, Verdict.SUPPORTED)


class StreamPositionTests(unittest.TestCase):
    def test_stream_is_rewound_after_inspection(self):
        # The caller hashes and stores the file next; both must start at byte 0.
        for name, content in (("letter.docx", DOCX), ("notes.txt", b"abc"), ("x.pdf", EXE)):
            with self.subTest(name=name):
                stream = io.BytesIO(content)
                stream.seek(3)
                inspect_file(name, stream, len(content), LIMIT)
                self.assertEqual(stream.tell(), 0)


if __name__ == "__main__":
    unittest.main()
