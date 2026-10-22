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
