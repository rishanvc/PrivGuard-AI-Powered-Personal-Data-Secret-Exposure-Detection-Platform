"""Generate samples/detection-demo/: synthetic files with known personal data (Cycle 5).

    backend/.venv/Scripts/python.exe samples/make_detection_demo.py

Every value is synthetic. Names are "Example" people. Aadhaar-format numbers
carry a valid Verhoeff check digit so they exercise the real checksum - like
any 12 digits one could coincide with an issued number, but alone, with no
name or other attribute, such a number identifies no one. "98765 43210" is
the placeholder common in Indian documentation; PANs are format-valid
inventions; email domains are invented or reserved (example.com).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from tests.engine import builders as b  # noqa: E402
from tests.engine.detection_corpus import aadhaar  # noqa: E402

OUT = ROOT / "detection-demo"
MAIL = "mailhost-synthetic.net"

EMPLOYEES = [
    ["Name", "Mobile", "Email", "Date of Birth", "Aadhaar", "PAN", "Gender", "Blood Group"],
    ["Asha Example", "98765 43210", f"asha.example@{MAIL}", "17/05/1990", aadhaar("23456789012"), "ABCPE1234F",
     "Female", "B+"],
    ["Ravi Example", "+91 98765 43211", f"ravi.example@{MAIL}", "03/11/1985", aadhaar("34567890123"), "BNZPM2501F",
     "Male", "O+"],
    ["Meera Example", "98765 43212", f"meera.example@{MAIL}", "1992-08-21", aadhaar("45678901234"), "CDQPK7788L",
     "Female", "B+"],
]

FILES = {
    "employees.csv": "".join(",".join(row) + "\r\n" for row in EMPLOYEES),
    "hr-letter.docx": b.docx_bytes(
        b.para(b.run("Dear Ms. Asha Example,"))
        + b.para(b.run("Employee ID: EMP-1042"))
        + b.para(b.run("PAN: ABCPE1234F"))
        + b.para(b.run("Date of birth: 3 March 1985"))
        + b.para(b.run("Residential address: 12 MG Road, Bengaluru 560001"))
        + b.para(b.run("PIN code: 560001"))
        + b.para(b.run("Mobile: +91 98765 43210"))
        + b.para(b.run("Questions? Write to hr@example.com")),
        creator="Synthetic Author",
    ),
    "notes.txt": (
        "Customer Name: Ravi Example Order ID: 4421\n"
        "Please call Asha Example about the invoice.\n"  # a name in prose: NOT found (known gap, D-028)
        f"UID {aadhaar('34567890123')} verified at the branch\n"
        "Passport No: K1234567\n"
        "Religion: Hindu\n"
    ),
    # Every line resembles personal data, and none of it is. Expected: no findings.
    "lookalikes.txt": (
        "Invoice 9876543210 paid in full\n"
        "Card 4111 1111 1111 1112\n"  # a published test card with one digit changed: fails Luhn
        "ISBN 978-0-306-40615-7\n"
        "Product code ABCDE1234F\n"
        "Use logo@2x.png on retina screens\n"
        "git clone git@github.com:synthetic-org/repo.git\n"
        "Meeting moved to 17/05/1990\n"
        "First Name: Last Name: Email:\n"
        f"Order reference {aadhaar('56789012345', '')}\n"
        "Passport photo: attached\n"
    ),
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, content in FILES.items():
        data = content.encode("utf-8") if isinstance(content, str) else content
        (OUT / name).write_bytes(data)
        print(f"wrote {OUT.name}/{name} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
