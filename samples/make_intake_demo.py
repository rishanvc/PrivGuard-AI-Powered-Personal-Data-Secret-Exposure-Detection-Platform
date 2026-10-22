"""Generate samples/intake-demo/: synthetic files that exercise every intake outcome.

    python samples/make_intake_demo.py

Every file is synthetic - no real data. Safe to delete and regenerate.
See samples/README.md for the expected result of uploading each file.
"""

import base64
import io
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parent / "intake-demo"

NOTES = b"Synthetic meeting notes for PrivGuard intake testing.\nContains no real data.\n"

# A real 1x1 PNG image.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

# Only the 2-byte Windows-executable signature plus zeros. NOT a runnable
# program - just enough for PrivGuard to see "this is not a PDF".
FAKE_EXE = b"MZ" + b"\x00" * 62


def make_pdf(text: str) -> bytes:
    """A minimal but valid one-page PDF with a correct cross-reference table."""
    stream = f"BT /F1 16 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref))
    return out.getvalue()


def make_docx(text: str) -> bytes:
    """A minimal but valid Word document (opens in Word / LibreOffice)."""
    parts = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>"
        ),
        "word/document.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
        ),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def make_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("inside-the-archive.txt", "Synthetic file inside an archive.\n")
    return buffer.getvalue()


FILES = {
    "notes.txt": NOTES,
    "notes_copy.txt": NOTES,  # identical bytes -> duplicate ("_" sorts after ".", so usually second)
    "empty.txt": b"",
    "report.pdf": make_pdf("Synthetic report for PrivGuard intake testing."),
    "letter.docx": make_docx("Synthetic letter for PrivGuard intake testing. No real data."),
    "invoice.pdf": FAKE_EXE,
    "photo.png": PNG,
    "backup.zip": make_zip(),
    "src/app.py": b'print("Synthetic application for PrivGuard intake testing.")\n',
    "config/settings.yaml": b"# Synthetic configuration\ndebug: false\nregion: demo\n",
    "config/sample.env": b"# Synthetic environment file - no real values\nAPP_MODE=demo\nLOG_LEVEL=info\n",
}


def main() -> None:
    for relative, content in FILES.items():
        path = OUT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        print(f"  {relative:<22} {len(content):>6} bytes")
    print(f"Wrote {len(FILES)} files to {OUT}")


if __name__ == "__main__":
    main()
