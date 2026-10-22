"""Generate samples/extraction-demo/: synthetic files that exercise each extractor.

    backend/.venv/Scripts/python.exe samples/make_extraction_demo.py

Uses the same builders as the engine tests (backend/tests/engine/builders.py),
and openpyxl - so run it with the backend's virtual environment.

Every value is synthetic: names are "Example" people, emails use the reserved
example.com domain, and phone numbers come from the UK range Ofcom reserves
for fiction (020 7946 0xxx). There are no credentials of any kind.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from tests.engine import builders as b  # noqa: E402

OUT = ROOT / "extraction-demo"

FILES = {
    "staff.xlsx": b.xlsx_bytes(
        {
            "Staff": [
                ["Name", "Email", "Phone", "Report"],
                ["Ana Example", "ana.example@example.com", "+44 20 7946 0001",
                 '=HYPERLINK("https://intranet.example.com/reports/42","Q3 report")'],
                ["Ben Example", "ben.example@example.com", "+44 20 7946 0002", None],
            ],
            "Archive": [["Former employee"], ["Cara Example"]],
        },
        hidden=("Archive",),
    ),
    "letter.docx": b.docx_bytes(
        b.para(b.run("Dear Ana Example,"))
        + b.para(b.run("Thank you for your enquiry. "), b.deleted_run("Your previous account was 00-11-22 12345678."))
        + b.para(b.run("Your details are on our "), *[b.field_runs('HYPERLINK "https://intranet.example.com/customers/42"', "customer portal")])
        + b.table([["Customer", "Ana Example"], ["Reference", "CUST-0042"]])
        + b.commented_para("Kind regards, Synthetic Corp"),
        header="Synthetic Corp - Internal",
        footer="Confidential",
        comments=[("Synthetic Reviewer", "Remove the old account number before sending.")],
        creator="Synthetic Author",
    ),
    "deck.pptx": b.pptx_bytes(
        {1: ["Quarterly review", "Revenue up 4%"], 2: ["Customer escalations"]},
        notes={2: "Call Ana Example on +44 20 7946 0001 before the meeting."},
        creator="Synthetic Author",
    ),
    "report.pdf": b.pdf_bytes(
        ["Synthetic quarterly report\nPrepared for internal use", "", "Contact: ana.example@example.com"],
        info={"Author": "Synthetic Author", "Title": "Quarterly report"},
    ),
    "scanned.pdf": b.pdf_bytes(["", ""]),
    "customers.csv": (
        'name,email,notes\r\n'
        'Ana Example,ana.example@example.com,"Prefers email.\r\nAvailable mornings."\r\n'
        'Ben Example,ben.example@example.com,Call after 3pm\r\n'
    ).encode("utf-8"),
    "legacy-notes.txt": "Cafe visit notes — price €12, contact Ana Example.\r\n".replace("Cafe", "Café").encode("cp1252"),
    "windows-export-utf16.txt": "2026-01-01 09:00 login ana.example\r\n2026-01-01 09:05 export started\r\n".encode("utf-16"),
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, content in FILES.items():
        (OUT / name).write_bytes(content)
        print(f"  {name:<20} {len(content):>6} bytes")
    print(f"Wrote {len(FILES)} files to {OUT}")


if __name__ == "__main__":
    main()
