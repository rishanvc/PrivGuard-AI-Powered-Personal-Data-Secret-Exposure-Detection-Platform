"""Word (DOCX) and PowerPoint (PPTX) text, read straight from their XML (FR-024, FR-026).

An Office file is a ZIP of XML "parts". Reading the parts ourselves, rather
than through python-docx, captures text that Word does not DISPLAY but the file
still CONTAINS: tracked deletions, field codes, comments, footnotes, headers,
footers, document properties - and PowerPoint speaker notes (FR-099).

All XML goes through defusedxml with DTDs forbidden: Office XML never needs a
DTD or entity, so refusing them costs nothing and closes the XML-bomb and
external-entity attacks.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from xml.etree.ElementTree import ParseError

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring, iterparse

from .base import ExtractionError, Limits, NotSupported, Report, Segment

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
RELATIONSHIP = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"

_PROPERTY_FIELDS = frozenset(
    {"creator", "lastModifiedBy", "title", "subject", "keywords", "description", "category", "Company", "Manager"}
)
_REFUSED_XML = (
    "The document contains XML declarations (a DTD or entities) that Office files never "
    "need; it was not processed."
)
_DAMAGED_XML = "The document's internal XML is damaged."


# ------------------------------------------------------------------ ZIP safety

def check_zip_safety(path: str, limits: Limits) -> None:
    """Refuse ZIP bombs BEFORE decompressing anything, from the declared sizes."""
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
    except (zipfile.BadZipFile, OSError):
        raise ExtractionError("The file is not a valid Office document.") from None

    total = 0
    for entry in entries:
        total += entry.file_size
        if entry.file_size > limits.max_part_bytes:
            raise ExtractionError("A part of this document is too large to process safely.")
        if entry.file_size > limits.ratio_floor and entry.file_size > limits.max_ratio * max(entry.compress_size, 1):
            raise ExtractionError("A part of this document is compressed suspiciously well (a possible ZIP bomb).")
    if total > limits.max_total_uncompressed:
        raise ExtractionError("This document would expand to more data than PrivGuard processes safely.")


class _Bounded:
    """Stops reading at `limit` bytes even if a ZIP entry lies about its size."""

    def __init__(self, raw, limit: int):
        self._raw, self._left = raw, limit

    def read(self, size: int = -1) -> bytes:
        want = self._left + 1 if size is None or size < 0 else min(size, self._left + 1)
        data = self._raw.read(want)
        self._left -= len(data)
        if self._left < 0:
            raise ExtractionError("A part of this document is larger than it claims (a possible ZIP bomb).")
        return data


def _read_part(archive: zipfile.ZipFile, name: str, limits: Limits) -> bytes:
    with archive.open(name) as raw:
        return _Bounded(raw, limits.max_part_bytes).read()


# ------------------------------------------------------------------ paragraphs

def _paragraphs(stream, *, para, texts, breaks=(), deleted=None, field=None, tab=None, props=None, root_ns=None):
    """Yield (number, {"text", "deleted", "field"}) per paragraph, in document order.

    A stack keeps paragraphs apart: a text box puts a whole paragraph INSIDE
    another one, and collecting "all text under this paragraph" would count
    the text box twice.
    """
    stack: list[tuple[int, dict[str, list[str]]]] = []
    number = 0
    in_props = 0
    first = True
    for event, element in iterparse(stream, events=("start", "end"), forbid_dtd=True):
        tag = element.tag
        if event == "start":
            if first:
                first = False
                if root_ns and not tag.startswith(root_ns):
                    raise NotSupported("This document uses the 'Strict Open XML' format, which PrivGuard cannot read yet.")
            if tag == para:
                number += 1
                stack.append((number, {"text": [], "deleted": [], "field": []}))
            elif tag == props:
                in_props += 1
            continue

        # "end" events: the element's text is complete now.
        if tag == props:
            in_props -= 1
        elif not stack:
            continue
        elif tag in texts:
            stack[-1][1]["text"].append(element.text or "")
        elif tag == deleted:
            stack[-1][1]["deleted"].append(element.text or "")
        elif tag == field:
            stack[-1][1]["field"].append(element.text or "")
        elif tag == tab and not in_props:  # in paragraph properties, <w:tab> is a tab STOP
            stack[-1][1]["text"].append("\t")
        elif tag in breaks:
            stack[-1][1]["text"].append("\n")
        elif tag == para:
            paragraph_number, buffers = stack.pop()
            element.clear()  # keep memory flat on long documents (NFR-004)
            yield paragraph_number, {key: "".join(parts) for key, parts in buffers.items()}


def _word_paragraphs(stream, root_ns=None):
    return _paragraphs(
        stream, para=W + "p", texts={W + "t"}, breaks={W + "br", W + "cr"},
        deleted=W + "delText", field=W + "instrText", tab=W + "tab", props=W + "pPr", root_ns=root_ns,
    )


def _drawing_paragraphs(stream):
    return _paragraphs(stream, para=A + "p", texts={A + "t"}, breaks={A + "br"})


def _attribute_values(stream, tag: str, attribute: str):
    for _, element in iterparse(stream, events=("end",), forbid_dtd=True):
        if element.tag == tag and element.get(attribute):
            yield element.get(attribute)


# ------------------------------------------------------------------ package structure

def _number(name: str) -> int:
    match = re.search(r"(\d+)\.xml$", name)
    return int(match.group(1)) if match else 0


def _relationships(archive, part: str, names: set[str], limits: Limits) -> dict[str, tuple[str, str]]:
    """rId -> (relationship type, part name inside the ZIP)."""
    folder, file_name = posixpath.split(part)
    rels_name = posixpath.join(folder, "_rels", file_name + ".rels")
    if rels_name not in names:
        return {}
    result = {}
    for rel in fromstring(_read_part(archive, rels_name, limits), forbid_dtd=True).iter(RELATIONSHIP):
        target = rel.get("Target", "")
        if rel.get("TargetMode") == "External":
            continue
        resolved = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(folder, target))
        result[rel.get("Id")] = (rel.get("Type", ""), resolved)
    return result


def _properties(archive, names: set[str], limits: Limits):
    """Author, title, company... from docProps: personal data hides in metadata too."""
    for part in ("docProps/core.xml", "docProps/app.xml"):
        if part not in names:
            continue
        for element in fromstring(_read_part(archive, part, limits), forbid_dtd=True).iter():
            local = element.tag.rsplit("}", 1)[-1]
            if local in _PROPERTY_FIELDS and element.text and element.text.strip():
                yield Segment(element.text.strip(), {"part": "properties", "field": local})


def _guard(extract):
    """Turn ZIP and XML problems into fixed, user-facing errors."""

    def wrapper(path: str, report: Report, limits: Limits):
        check_zip_safety(path, limits)
        try:
            yield from extract(path, report, limits)
        except DefusedXmlException:
            raise ExtractionError(_REFUSED_XML) from None
        except ParseError:
            raise ExtractionError(_DAMAGED_XML) from None
        except zipfile.BadZipFile:
            raise ExtractionError("The file is not a valid Office document.") from None
        # Deliberately NOT caught: KeyError and the like. Entries are checked
        # before they are opened, so one of those would be a bug in PrivGuard,
        # not a broken file - the driver logs its type instead of blaming the file.

    wrapper.__name__ = extract.__name__
    return wrapper


# ------------------------------------------------------------------ DOCX

def _docx_parts(names: set[str]) -> list[tuple[str, str]]:
    def numbered(prefix: str, label: str):
        found = sorted((n for n in names if re.fullmatch(rf"word/{prefix}\d+\.xml", n)), key=_number)
        return [(name, f"{label} {i}") for i, name in enumerate(found, start=1)]

    order = [("word/document.xml", "body"), *numbered("header", "header"), *numbered("footer", "footer"),
             ("word/footnotes.xml", "footnotes"), ("word/endnotes.xml", "endnotes"), ("word/comments.xml", "comments")]
    return [(name, label) for name, label in order if name in names]


@_guard
def extract_docx(path: str, report: Report, limits: Limits):
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "word/document.xml" not in names:
            raise ExtractionError("This is not a valid Word document.")

        for name, label in _docx_parts(names):
            report.count("parts")
            with archive.open(name) as raw:
                paragraphs = _word_paragraphs(_Bounded(raw, limits.max_part_bytes), root_ns=W if label == "body" else None)
                for number, text in paragraphs:
                    report.count("paragraphs")
                    where = {"part": label, "paragraph": number}
                    if text["text"].strip():
                        yield Segment(text["text"], where)
                    if text["deleted"].strip():
                        report.count("tracked_deletions")
                        report.note("Tracked deletions were read: text deleted with Track Changes on is still inside the file.")
                        yield Segment(text["deleted"], {**where, "kind": "deleted"})
                    if text["field"].strip():
                        yield Segment(text["field"].strip(), {**where, "kind": "field code"})

            if label == "comments":
                with archive.open(name) as raw:
                    authors = sorted(set(_attribute_values(_Bounded(raw, limits.max_part_bytes), W + "comment", W + "author")))
                report.note("Comments were read, including their authors' names.")
                for author in authors:
                    yield Segment(author, {"part": "comments", "field": "author"})

        yield from _properties(archive, names, limits)


# ------------------------------------------------------------------ PPTX

def _slide_order(archive, names: set[str], limits: Limits) -> list[str]:
    """Slide parts in PRESENTATION order - "slide 3" must mean what PowerPoint shows as slide 3,
    which is not necessarily slide3.xml once slides have been reordered."""
    rels = _relationships(archive, "ppt/presentation.xml", names, limits)
    presentation = fromstring(_read_part(archive, "ppt/presentation.xml", limits), forbid_dtd=True)
    order = []
    for slide_id in presentation.iter(P + "sldId"):
        _, target = rels.get(slide_id.get(R_ID), ("", ""))
        if target in names:
            order.append(target)
    return order


@_guard
def extract_pptx(path: str, report: Report, limits: Limits):
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "ppt/presentation.xml" not in names:
            raise ExtractionError("This is not a valid PowerPoint presentation.")

        for number, slide in enumerate(_slide_order(archive, names, limits), start=1):
            report.count("slides")
            with archive.open(slide) as raw:
                for _, text in _drawing_paragraphs(_Bounded(raw, limits.max_part_bytes)):
                    if text["text"].strip():
                        yield Segment(text["text"], {"slide": number, "part": "slide"})

            notes = next((target for kind, target in _relationships(archive, slide, names, limits).values()
                          if kind.endswith("/notesSlide") and target in names), None)
            if notes:
                report.count("slides_with_notes")
                report.note("Speaker notes were read: they are invisible during a presentation but travel with the file.")
                with archive.open(notes) as raw:
                    for _, text in _drawing_paragraphs(_Bounded(raw, limits.max_part_bytes)):
                        if text["text"].strip():
                            yield Segment(text["text"], {"slide": number, "part": "notes"})

        yield from _properties(archive, names, limits)
