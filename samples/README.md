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
