"""Text extraction per format (FR-020 to FR-029). Runs WITHOUT Django.

Every file is synthetic and written WITHOUT an extension - exactly how
uploads are stored (D-016) - so extractors can never rely on file names.
"""

import csv
import os
import shutil
import tempfile
import unittest
from itertools import count
from unittest import mock

import pypdfium2 as pdfium

from privguard_engine.extractors import ExtractionStatus as S
from privguard_engine.extractors import Limits, extract_file
from privguard_engine.extractors.base import MISSING, UNREADABLE, ExtractionError, Segment, run_extractor

from . import builders as b

_names = count(1)


class ExtractionTestCase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="privguard-extract-")
        self.addCleanup(shutil.rmtree, self.folder, True)

    def store(self, content: bytes) -> str:
        path = os.path.join(self.folder, f"stored-{next(_names)}")  # no extension, like real storage
        with open(path, "wb") as handle:
            handle.write(content)
        return path

    def extract(self, content: bytes, file_type: str, limits: Limits | None = None):
        segments: list[Segment] = []
        result = extract_file(self.store(content), file_type, limits=limits, sink=segments.append)
        return result, segments

    @staticmethod
    def find(segments, text):
        return next(s for s in segments if s.text == text)


# ------------------------------------------------------------------ plain text

class TextTests(ExtractionTestCase):
    def test_lines_are_numbered_like_an_editor(self):
        result, segments = self.extract(b"first\r\nsecond\rthird\n\nfifth", "text")
        self.assertEqual(result.status, S.SUCCEEDED)
        self.assertEqual([(s.text, s.location["line"]) for s in segments],
                         [("first", 1), ("second", 2), ("third", 3), ("fifth", 5)])
        self.assertEqual(result.stats["lines"], 5)

    def test_byte_order_marks_decide_the_encoding(self):
        for codec in ("utf-8-sig", "utf-16", "utf-32"):
            with self.subTest(codec=codec):
                result, segments = self.extract("café\n".encode(codec), "text")
                self.assertEqual(segments[0].text, "café")
                self.assertEqual(result.stats["encoding"], codec)

    def test_invalid_utf8_falls_back_to_windows_1252_with_a_note(self):
        result, segments = self.extract("naïve café costs €5\n".encode("cp1252"), "text")
        self.assertEqual(result.status, S.SUCCEEDED)  # a note, not a failure
        self.assertEqual(segments[0].text, "naïve café costs €5")
        self.assertEqual(result.stats["encoding"], "windows-1252")
        self.assertTrue(any("not valid UTF-8" in note for note in result.notes))

    def test_a_bad_byte_after_the_first_megabyte_is_still_noticed(self):
        content = b"x" * (1024 * 1024 + 10) + b"\n" + "é".encode("cp1252")
        result, _ = self.extract(content, "code")
        self.assertEqual(result.stats["encoding"], "windows-1252")

    def test_blank_file_succeeds_and_says_no_text_was_found(self):
        result, segments = self.extract(b"   \n\n\t\n", "text")
        self.assertEqual((result.status, segments), (S.SUCCEEDED, []))
        self.assertIn("No text was found in this file.", result.notes)

    def test_character_limit_gives_partial(self):
        result, segments = self.extract(b"abcdefghij\n" * 5, "text", Limits(max_chars=25))
        self.assertEqual(result.status, S.PARTIAL)
        self.assertEqual(len(segments), 2)
        self.assertIn("characters", result.reason)


# ------------------------------------------------------------------ CSV

class CsvTests(ExtractionTestCase):
    def test_cells_carry_row_column_header_and_line(self):
        result, segments = self.extract(b"name,email\r\nAna Example,ana@example.com\r\n", "csv")
        self.assertEqual(result.status, S.SUCCEEDED)
        self.assertEqual(self.find(segments, "ana@example.com").location,
                         {"row": 2, "column": 2, "line": 2, "header": "email"})
        self.assertEqual(self.find(segments, "email").location, {"row": 1, "column": 2, "line": 1})

    def test_a_quoted_field_spanning_lines_reports_where_it_starts(self):
        _, segments = self.extract(b'id,note\n1,"first line\nsecond line"\n2,after\n', "csv")
        self.assertEqual(self.find(segments, "first line\nsecond line").location["line"], 2)
        self.assertEqual(self.find(segments, "after").location, {"row": 3, "column": 2, "line": 4, "header": "note"})

    def test_delimiters_are_sniffed(self):
        for separator, name in ((";", "semicolon"), ("\t", "tab"), ("|", "pipe")):
            with self.subTest(delimiter=name):
                result, segments = self.extract(f"name{separator}city\nAna{separator}Lisbon\n".encode(), "csv")
                self.assertEqual(self.find(segments, "Lisbon").location["header"], "city")
                self.assertEqual(result.stats["delimiter"], name)

    def test_cell_limit_gives_partial(self):
        result, segments = self.extract(b"a,b\n1,2\n3,4\n5,6\n", "csv", Limits(max_cells=3))
        self.assertEqual((result.status, len(segments)), (S.PARTIAL, 3))

    def test_field_beyond_the_parser_limit_gives_partial_and_restores_the_limit(self):
        before = csv.field_size_limit()
        content = b'a,b\n1,2\n3,"' + b"x" * (1024 * 1024 + 10) + b'"\n'
        result, segments = self.extract(content, "csv")
        self.assertEqual(result.status, S.PARTIAL)
        self.assertIn("stopped parsing as CSV", result.reason)
        self.assertTrue(any(s.text == "2" for s in segments))  # rows before the problem survived
        self.assertEqual(csv.field_size_limit(), before)


# ------------------------------------------------------------------ XLSX

class XlsxTests(ExtractionTestCase):
    def workbook(self, **kwargs):
        rows = [
            ["Name", "Contact", "Report"],
            ["Ana Example", "ana@example.com", '=HYPERLINK("https://example.com/r","report")'],
            ["Ben Example", 4111111111111111, None],
        ]
        return b.xlsx_bytes({"Staff": rows}, **kwargs)

    def test_cells_headers_and_formulas_as_written(self):
        result, segments = self.extract(self.workbook(), "xlsx")
        self.assertEqual(result.status, S.SUCCEEDED, result.reason)
        self.assertEqual(self.find(segments, "ana@example.com").location,
                         {"sheet": "Staff", "cell": "B2", "header": "Contact"})
        formula = next(s for s in segments if s.text.startswith("=HYPERLINK"))
        self.assertIn("https://example.com/r", formula.text)  # the formula, not its displayed result
        self.assertEqual(self.find(segments, "4111111111111111").location["cell"], "B3")
        self.assertEqual((result.stats["sheets"], result.stats["cells"]), (1, 8))

    def test_hidden_sheets_are_read_and_flagged(self):
        content = b.xlsx_bytes({"Visible": [["shown"]], "Archive": [["old value"]]}, hidden=("Archive",))
        result, segments = self.extract(content, "xlsx")
        self.assertTrue(self.find(segments, "old value").location["hidden"])
        self.assertNotIn("hidden", self.find(segments, "shown").location)
        self.assertEqual(result.stats["hidden_sheets"], 1)
        self.assertTrue(any("Hidden sheets" in note for note in result.notes))

    def test_a_stored_file_without_an_extension_is_readable(self):
        # Given a PATH, openpyxl refuses names without ".xlsx". The extractor
        # passes a file handle instead; this pins that behaviour.
        result, _ = self.extract(self.workbook(), "xlsx")
        self.assertEqual(result.status, S.SUCCEEDED)

    def test_damaged_workbook_fails_cleanly(self):
        broken = b.zip_bytes({"[Content_Types].xml": "<Types/>", "xl/workbook.xml": "not xml at all"})
        result, _ = self.extract(broken, "xlsx")
        self.assertEqual(result.status, S.FAILED)
        self.assertIn("could not be opened", result.reason)

    def test_a_part_larger_than_the_limit_is_refused_before_decompression(self):
        result, _ = self.extract(self.workbook(), "xlsx", Limits(max_part_bytes=50))
        self.assertEqual(result.status, S.FAILED)
        self.assertIn("too large", result.reason)

    def test_a_suspicious_compression_ratio_is_refused(self):
        repetitive = b.xlsx_bytes({"Data": [["aaaaaaaaaa"] * 10 for _ in range(2000)]})
        result, _ = self.extract(repetitive, "xlsx", Limits(ratio_floor=1000, max_ratio=5))
        self.assertEqual(result.status, S.FAILED)
        self.assertIn("ZIP bomb", result.reason)

    def test_cell_limit_gives_partial(self):
        result, segments = self.extract(self.workbook(), "xlsx", Limits(max_cells=4))
        self.assertEqual((result.status, len(segments)), (S.PARTIAL, 4))


# ------------------------------------------------------------------ DOCX

class DocxTests(ExtractionTestCase):
    def test_body_table_header_footer_and_properties(self):
        content = b.docx_bytes(
            b.para(b.run("Dear customer")) + b.table([["Account", "12345"]]),
            header="Synthetic Corp", footer="Confidential footer", creator="Synthetic Author",
        )
        result, segments = self.extract(content, "docx")
        self.assertEqual(result.status, S.SUCCEEDED, result.reason)
        self.assertEqual(self.find(segments, "Dear customer").location, {"part": "body", "paragraph": 1})
        self.assertEqual(self.find(segments, "12345").location, {"part": "body", "paragraph": 3})
        self.assertEqual(self.find(segments, "Synthetic Corp").location["part"], "header 1")
        self.assertEqual(self.find(segments, "Confidential footer").location["part"], "footer 1")
        self.assertEqual(self.find(segments, "Synthetic Author").location, {"part": "properties", "field": "creator"})

    def test_tracked_deletion_is_extracted_and_marked(self):
        content = b.docx_bytes(b.para(b.run("Kept text. "), b.deleted_run("Removed account 98765")))
        result, segments = self.extract(content, "docx")
        self.assertEqual(self.find(segments, "Kept text. ").location, {"part": "body", "paragraph": 1})
        self.assertEqual(self.find(segments, "Removed account 98765").location["kind"], "deleted")
        self.assertEqual(result.stats["tracked_deletions"], 1)

    def test_field_code_is_extracted_separately_from_the_shown_text(self):
        content = b.docx_bytes(b.para(b.field_runs('HYPERLINK "https://example.com/private"', "link")))
        _, segments = self.extract(content, "docx")
        self.assertEqual(self.find(segments, "link").location, {"part": "body", "paragraph": 1})
        code = self.find(segments, 'HYPERLINK "https://example.com/private"')
        self.assertEqual(code.location["kind"], "field code")

    def test_comments_and_their_authors(self):
        content = b.docx_bytes(b.commented_para("Total: 500"), comments=[("Synthetic Reviewer", "Check this figure")])
        result, segments = self.extract(content, "docx")
        self.assertEqual(self.find(segments, "Check this figure").location["part"], "comments")
        self.assertEqual(self.find(segments, "Synthetic Reviewer").location, {"part": "comments", "field": "author"})
        self.assertTrue(any("authors' names" in note for note in result.notes))

    def test_text_box_text_is_counted_once(self):
        _, segments = self.extract(b.docx_bytes(b.text_box_para("Outer", "Inner box text")), "docx")
        texts = [s.text for s in segments]
        self.assertEqual(texts.count("Inner box text"), 1)
        self.assertIn("Outer", texts)  # not "OuterInner box text"

    def test_tab_stop_definitions_do_not_become_text(self):
        _, segments = self.extract(b.docx_bytes(b.tab_stop_para("Phone:", "0000")), "docx")
        self.assertEqual(segments[0].text, "Phone:\t0000")  # one tab, from the run only

    def test_xml_with_a_dtd_is_refused(self):
        bomb = ('<?xml version="1.0"?><!DOCTYPE w:document [<!ENTITY a "lol">]>'
                f'<w:document xmlns:w="{b.W_NS}"><w:body><w:p><w:r><w:t>&a;</w:t></w:r></w:p></w:body></w:document>')
        result, segments = self.extract(b.docx_bytes("", document_xml=bomb), "docx")
        self.assertEqual((result.status, segments), (S.FAILED, []))
        self.assertIn("DTD or entities", result.reason)

    def test_damaged_xml_fails_cleanly(self):
        broken = f'<w:document xmlns:w="{b.W_NS}"><w:body><w:p>'
        result, _ = self.extract(b.docx_bytes("", document_xml=broken), "docx")
        self.assertEqual(result.status, S.FAILED)
        self.assertIn("damaged", result.reason)

    def test_strict_open_xml_is_reported_as_not_supported(self):
        strict = ('<w:document xmlns:w="http://purl.oclc.org/ooxml/wordprocessingml/main">'
                  "<w:body><w:p><w:r><w:t>text</w:t></w:r></w:p></w:body></w:document>")
        result, _ = self.extract(b.docx_bytes("", document_xml=strict), "docx")
        self.assertEqual(result.status, S.NOT_SUPPORTED)


# ------------------------------------------------------------------ PPTX

class PptxTests(ExtractionTestCase):
    def test_slides_follow_presentation_order_and_notes_are_read(self):
        content = b.pptx_bytes({1: ["From file one"], 2: ["From file two"]}, order=[2, 1],
                               notes={1: "Speaker note for file one"})
        result, segments = self.extract(content, "pptx")
        self.assertEqual(result.status, S.SUCCEEDED, result.reason)
        self.assertEqual(self.find(segments, "From file two").location, {"slide": 1, "part": "slide"})
        self.assertEqual(self.find(segments, "From file one").location, {"slide": 2, "part": "slide"})
        self.assertEqual(self.find(segments, "Speaker note for file one").location, {"slide": 2, "part": "notes"})
        self.assertEqual((result.stats["slides"], result.stats["slides_with_notes"]), (2, 1))

    def test_line_breaks_inside_a_paragraph_are_kept(self):
        _, segments = self.extract(b.pptx_bytes({1: ["Line one\nLine two"]}), "pptx")
        self.assertEqual(segments[0].text, "Line one\nLine two")


# ------------------------------------------------------------------ PDF

class PdfTests(ExtractionTestCase):
    def test_pages_are_numbered_and_a_textless_page_makes_it_partial(self):
        result, segments = self.extract(b.pdf_bytes(["Page one text", "", "Page three text"]), "pdf")
        self.assertEqual(result.status, S.PARTIAL)
        self.assertEqual([s.location["page"] for s in segments], [1, 3])
        self.assertIn("1 of 3 pages", result.reason)
        self.assertEqual((result.stats["pages"], result.stats["pages_without_text"]), (3, 1))

    def test_a_pdf_with_no_text_at_all_is_not_supported_yet(self):
        result, segments = self.extract(b.pdf_bytes(["", ""]), "pdf")
        self.assertEqual((result.status, segments), (S.NOT_SUPPORTED, []))
        self.assertIn("scanned", result.reason)

    def test_metadata_author_is_extracted(self):
        _, segments = self.extract(b.pdf_bytes(["Body"], info={"Author": "Synthetic Author"}), "pdf")
        self.assertEqual(self.find(segments, "Synthetic Author").location, {"part": "properties", "field": "author"})

    def test_password_protected_pdf_maps_to_not_supported(self):
        # Tests OUR mapping of PDFium's error code; a real encrypted fixture is a known gap.
        locked = pdfium.PdfiumError("locked", err_code=pdfium.raw.FPDF_ERR_PASSWORD)
        with mock.patch("privguard_engine.extractors.pdf.pdfium.PdfDocument", side_effect=locked):
            result, _ = self.extract(b"%PDF-1.7", "pdf")
        self.assertEqual(result.status, S.NOT_SUPPORTED)
        self.assertIn("password", result.reason)

    def test_damaged_pdf_fails_cleanly(self):
        result, _ = self.extract(b"%PDF-1.4 this is not really a pdf", "pdf")
        self.assertEqual(result.status, S.FAILED)
        self.assertIn("damaged", result.reason)

    def test_page_limit_gives_partial(self):
        result, segments = self.extract(b.pdf_bytes(["one", "two", "three"]), "pdf", Limits(max_pages=2))
        self.assertEqual((result.status, len(segments)), (S.PARTIAL, 2))
        self.assertIn("first 2 of 3 pages", result.reason)


# ------------------------------------------------------------------ the driver's own rules

class DriverTests(ExtractionTestCase):
    def test_unknown_file_type_is_not_supported(self):
        result = extract_file(self.store(b"x"), "pptm")
        self.assertEqual(result.status, S.NOT_SUPPORTED)

    def test_errors_in_the_consumer_propagate(self):
        # A bug in detection must surface as a bug, not as "this file is damaged".
        def broken_sink(segment):
            raise RuntimeError("detector bug")

        with self.assertRaises(RuntimeError):
            extract_file(self.store(b"hello\n"), "text", sink=broken_sink)

    def test_unexpected_errors_never_leak_their_message(self):
        def leaky_extractor(path, report, limits):
            raise ValueError("SYNTHETIC-SECRET-FROM-INSIDE-THE-FILE")
            yield  # pragma: no cover - makes this a generator

        with self.assertLogs("privguard_engine.extractors.base", "WARNING"):
            result = run_extractor(leaky_extractor, "unused", Limits())
        self.assertEqual((result.status, result.reason), (S.FAILED, UNREADABLE))

    def test_missing_file_is_reported(self):
        result = extract_file(os.path.join(self.folder, "missing"), "text")
        self.assertEqual((result.status, result.reason), (S.FAILED, MISSING))

    def test_an_error_after_some_text_gives_partial(self):
        def half_readable(path, report, limits):
            yield Segment("readable part", {"line": 1})
            raise ExtractionError("The rest was unreadable.")

        result = run_extractor(half_readable, "unused", Limits())
        self.assertEqual((result.status, result.reason), (S.PARTIAL, "The rest was unreadable."))

    def test_stopping_early_closes_the_extractor(self):
        state = {"closed": False}

        def endless(path, report, limits):
            try:
                while True:
                    yield Segment("0123456789", {"line": 1})
            finally:
                state["closed"] = True  # where a real extractor closes its file

        result = run_extractor(endless, "unused", Limits(max_chars=35))
        self.assertEqual(result.status, S.PARTIAL)
        self.assertTrue(state["closed"])


if __name__ == "__main__":
    unittest.main()
