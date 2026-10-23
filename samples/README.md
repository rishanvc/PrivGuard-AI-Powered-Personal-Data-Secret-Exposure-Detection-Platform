# Sample files

Synthetic files for trying PrivGuard by hand. **Nothing here is real data**, per SRS 12.4: never test PrivGuard with real personal information or real credentials.

## `intake-demo/` — file intake (Cycle 3)

Regenerate with `python samples/make_intake_demo.py`.

Upload the whole folder with **Choose a folder…** to see every intake outcome in one scan:

| File | Expected status | Why |
|---|---|---|
| `notes.txt` | Accepted | Plain text |
| `notes_copy.txt` | Skipped | Same bytes as `notes.txt`, so the content is stored and processed once (FR-017) |
| `empty.txt` | Skipped | Nothing to scan |
| `report.pdf` | Accepted | Valid PDF |
| `letter.docx` | Accepted | Valid Word document |
| `invoice.pdf` | **Rejected** | Named `.pdf`, but its bytes start like a Windows executable |
| `photo.png` | Unsupported | Image OCR is not available yet |
| `backup.zip` | Unsupported | Archives are not supported yet |
| `src/app.py` | Accepted | Source code |
| `config/settings.yaml` | Accepted | Configuration |
| `config/sample.env` | Accepted | Environment file |

**Totals: 11 files: 6 accepted, 1 rejected, 2 unsupported, 2 skipped.**

Which of the two identical notes files is the "duplicate" depends on the order the browser sends them; whichever arrives first is accepted. The totals are the same either way. `apps/scans/tests/test_samples.py` uploads this folder and checks it against this table.

`invoice.pdf` holds only the 2-byte `MZ` signature followed by zeros. It is not a runnable program.

## `extraction-demo/` — text extraction (Cycle 4)

Regenerate with `backend/.venv/Scripts/python.exe samples/make_extraction_demo.py`.

See exactly what PrivGuard extracts from any of them. This prints the text, which is fine here because it's all synthetic:

```bash
cd backend
.venv/Scripts/python.exe -m privguard_engine.extractors ../samples/extraction-demo/letter.docx
```

| File | Expected result | What it demonstrates |
|---|---|---|
| `staff.xlsx` | Succeeded | Every cell carries its column header; a formula is read **as written**, exposing the intranet URL behind "Q3 report"; the **hidden** sheet `Archive` is read and flagged |
| `letter.docx` | Succeeded | A **tracked deletion** (an old account number Word no longer shows), a **field code** hiding an intranet URL, header, footer, table, a comment and its author, and the document's author |
| `deck.pptx` | Succeeded | **Speaker notes** on slide 2. A minimal file built for extraction only: PowerPoint itself may not open it |
| `report.pdf` | **Partial** | Page 2 has no text, standing in for a scanned page. Author and title are read from metadata |
| `scanned.pdf` | **Not supported** | No text layer at all; it needs OCR (Cycle 8) |
| `customers.csv` | Succeeded | Header names per cell; a quoted note spanning two lines, so the next row starts on line 4 |
| `legacy-notes.txt` | Succeeded, with a note | Windows-1252 rather than UTF-8, read with a fallback |
| `windows-export-utf16.txt` | Succeeded | UTF-16 with a byte-order mark |

All values are synthetic: "Example" names, the reserved `example.com` domain, and UK numbers from the range Ofcom reserves for fiction (020 7946 0xxx). There are no credentials of any kind. `backend/tests/engine/test_extraction_samples.py` checks this table against the real extractors.

## `detection-demo/` — personal data detection (Cycle 5)

Regenerate with `backend/.venv/Scripts/python.exe samples/make_detection_demo.py`.

Upload all four files as one scan to see detection in the app. To see the findings for one file on the command line (masked values only, never the file's text):

```bash
cd backend
.venv/Scripts/python.exe -m privguard_engine.detectors ../samples/detection-demo/employees.csv
```

| File | Findings | What it demonstrates |
|---|---|---|
| `employees.csv` | **22** | A column per kind of personal data; the column header supplies the context. Aadhaar numbers pass the Verhoeff checksum. "Female" and "B+" each appear twice, so each is **one** finding with 2 occurrences; both are hidden completely as `****` |
| `hr-letter.docx` | **9** | Values found by their **labels** in running text: a salutation, employee ID, PAN, date of birth, address, PIN code and mobile number, plus the document's author. `hr@example.com` is found with confidence 0.40, because `example.com` is reserved for documentation |
| `notes.txt` | **4** | "Customer Name: Ravi Example Order ID: 4421": the name stops where the next field starts. "Please call Asha Example…" is **not** found: a name in prose with no label is a known gap (D-028). Religion is flagged as special-category data |
| `lookalikes.txt` | **0** | Every line *resembles* personal data: an invoice number that is a valid mobile number, a card number, an ISBN, a non-PAN product code, `logo@2x.png`, an SSH remote, a date without a birth label, a blank form, a bare 12-digit number that passes the Aadhaar checksum |

**Totals: 35 findings.** Names are "Example" people; "98765 43210" is the placeholder common in Indian documentation; PANs are format-valid inventions; email domains are invented (`mailhost-synthetic.net`) or reserved (`example.com`). Aadhaar-format numbers carry a valid check digit: like any 12 digits, one could coincide with an issued number, but on its own it identifies no one. `backend/tests/engine/test_detection_samples.py` checks this table against the real detectors.
