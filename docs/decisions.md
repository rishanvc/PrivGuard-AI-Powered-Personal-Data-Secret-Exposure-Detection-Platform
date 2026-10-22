# PrivGuard — Design Decisions

A running log of decisions that shape the implementation, especially where the
SRS leaves room for interpretation. Each entry records what was decided, why,
and what it costs. `PrivGuard_SRS.md` remains the source of truth for
requirements; this file records *how* they are being met.

---

## Cycle 1 — Project Foundation

### D-001 · MIT license, permissive dependencies only
- **Decision:** PrivGuard is MIT-licensed. Runtime dependencies must be MIT, BSD, Apache-2.0, or MPL-2.0.
- **Why:** The repository is public, and the project is currently non-commercial but may not stay that way. AGPL is triggered by distribution and network use, not by commerce, so an AGPL dependency would force the whole project to AGPL.
- **Consequences:** PyMuPDF (AGPL-3.0) is excluded. PDF extraction will use `pdfplumber`/`pypdf` (Cycle 4); PDF redaction will rasterize pages via `pypdfium2` (Cycle 10).
  *Superseded in Cycle 4 by D-022: `pypdfium2` handles extraction as well; `pdfplumber` itself depends on `pypdfium2`.*
- **Note:** `psycopg` is LGPL-3.0, which is acceptable. LGPL copyleft stops at the library boundary, and a dynamically imported, user-replaceable package does not affect PrivGuard's license. Separately invoked GPL tools (a binary we run and read output from) are likewise not linked.

### D-002 · `privguard_engine` is framework-free
- **Decision:** All extraction, detection, risk, and redaction logic lives in `backend/privguard_engine/`, which never imports Django.
- **Why:** NFR-039 requires detection rules to be testable without the web application. Importing Django would pull in settings and a database connection.
- **Consequences:** Django apps call into the engine; the engine never calls back. Data crosses the boundary as plain Python objects.

### D-003 · Custom User model from the first migration
- **Decision:** `AUTH_USER_MODEL = "accounts.User"` with a `role` field, created in Cycle 1.
- **Why:** FR-004 needs roles, and Django cannot swap the user model after the first migration without rebuilding the database.

### D-004 · All runtime data under `backend/var/`
- **Decision:** Uploads, extracted text, redacted copies, reports, and scratch files live under one root, ignored by a single anchored `.gitignore` rule.
- **Why:** NFR-023 (controlled locations) and FR-114 (retention deletion become one subtree operation). Unanchored rules such as `scans/` were found to also ignore source directories like `backend/apps/scans/`.

### D-005 · Direct CORS rather than the Vite dev proxy
- **Decision:** The frontend calls `http://localhost:8000/api` directly; Django allows the Vite origin via `django-cors-headers`.
- **Why:** NFR-017 asks for configured cross-origin access, and it keeps the client/server boundary explicit.
- **Consequence:** Always browse at `localhost`, not `127.0.0.1`. Cookies are scoped by host, so the two behave as different sites.

### D-006 · JavaScript, not TypeScript
- **Decision:** The frontend uses plain JSX.
- **Why:** SRS 5.2 specifies React/Vite/Tailwind/Router without TypeScript; changing the agreed stack is the project owner's call.

### D-007 · Deny-by-default API permissions
- **Decision:** `DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]`. Public endpoints opt out explicitly with `AllowAny`.
- **Why:** NFR-007. Forgetting a permission class then locks an endpoint down instead of exposing it.

---

## Cycle 2 — Authentication and Permissions

### D-008 · Session cookies, not tokens or JWT
- **Decision:** Django sessions in `HttpOnly`, `SameSite=Lax` cookies, with CSRF tokens. Session lifetime 8 hours (configurable).
- **Why:** From Cycle 5 onward the UI renders context previews extracted from untrusted files. If an escaping bug ever allows script injection, a token in JS-readable storage could be stolen; an `HttpOnly` cookie cannot be read by script. Logout revokes the session server-side immediately, which a JWT cannot do without a blocklist. FR-006 specifies "sessions". No new dependency.
- **Costs:** CSRF handling in the SPA; the CSRF token must be refreshed after login because `login()` rotates it.

### D-009 · Least privilege: no administrator bypass on ownership
- **Decision:** Administrators manage users, settings, and policy, but cannot open other users' scans or findings.
- **Why:** The SRS is silent; FR-005 permits access only to owners or *explicitly* authorized users. Findings describe sensitive data even when masked, so an admin account should not be a skeleton key.
- **Consequence:** Oversight features, if needed later, must be designed as explicit sharing.

### D-010 · Log in with username or email
- **Decision:** A custom backend (`EmailOrUsernameBackend`) accepts either. Email is unique case-insensitively among non-blank emails (`uniq_user_email_ci`).
- **Why:** SRS 5.1.1 specifies a "username or email" field. Without case-insensitive uniqueness, email login would be ambiguous.

### D-011 · Ownership enforced by queryset scoping (404, not 403)
- **Decision:** `OwnedQuerysetMixin` filters querysets to `request.user`; `IsOwner` is a second, object-level check.
- **Why:** A 403 confirms that an ID exists; a 404 reveals nothing. `perform_create` stamps the owner server-side so clients cannot assign ownership to someone else.

### D-012 · Registration disabled by default
- **Decision:** `ALLOW_REGISTRATION=False`. Accounts are created with `createsuperuser` or the Django admin. Registered users always start as General User; `role` is not client-writable.
- **Why:** FR-007 (local single-user mode) and FR-001 ("where registration is enabled").

### D-013 · Login audit logging deferred to Cycle 11
- **Decision:** Login/logout events are not yet recorded.
- **Why:** FR-117 forbids logging raw credentials, and users sometimes type a password into the username field. Recording failed-login identifiers safely needs the AuditLog design in Cycle 11.

---

## Cycle 3 — File Upload and Inventory

### D-014 · File type decided by content, not by name
- **Decision:** `privguard_engine.intake` checks magic bytes, Office (ZIP) structure, and a NUL-byte text heuristic. The extension says what a file *claims* to be; the bytes decide whether the claim holds. Hand-written signatures, no dependency.
- **"Supported" means "PrivGuard can process it."** PPTX, images (until OCR) and archives are recognised but reported as unsupported with a specific reason, rather than accepted and silently not scanned (FR-013).
- **Limitation:** validation is not safety — polyglot files are valid as two formats. Safety comes from never executing content (NFR-011).

### D-015 · Upload size enforced in middleware, from Content-Length
- **Decision:** `RequestSizeLimitMiddleware` returns 413 when the declared size exceeds the per-scan limit, before anything reads the body. File count is capped by Django's parser; per-file size is checked per file so one oversized file doesn't sink the scan (NFR-028).
- **Why middleware:** DRF's CSRF check reads `request.POST`, which parses the entire multipart body onto disk before any view code runs.
- **Why Content-Length suffices:** under WSGI, Django never reads past the declared length. ASGI deployments need a server-level limit too (Cycle 12).
- **Correction:** Cycle 1's settings claimed `DATA_UPLOAD_MAX_MEMORY_SIZE` limited request bodies. It does not apply to file data (verified in Django's source); the comment was corrected.

### D-016 · Private storage under random names
- **Decision:** accepted files are stored as `var/uploads/<user>/<scan>/<random hex>` in a storage with **no URL**. The uploader's filename never reaches the filesystem; a sanitised display name is kept in the database. Uploads do not use `MEDIA_ROOT`. Spooled temp files go to `var/tmp`, not the system temp folder.
- **Why:** filenames are attacker-controlled (traversal, reserved device names, bidi spoofing); a URL-less storage can't be exposed by a stray `static()` route.

### D-017 · UUID primary keys for scans and files
- **Why:** sequential IDs leak how many scans exist and invite guessing. Ownership checks already return 404; UUIDs remove the leak too.

### D-018 · Lifecycle transitions by compare-and-swap; Start only queues
- **Decision:** status changes use a conditional `UPDATE ... WHERE status IN (...)`, so of two simultaneous requests exactly one succeeds. In Cycle 3, Start moves a draft to `queued`; nothing processes it yet.
- **Why defer the worker:** there is no work to run until extraction exists, and the choice should be made knowing how long scans take. Django 6.1's built-in tasks framework ships only immediate and dummy backends, so Cycle 4 will add a real (database-backed) worker backend.

### D-019 · Deletion now, files before records
- **Decision:** `DELETE /api/scans/{id}/` was pulled forward from Cycle 11, because Cycle 3 is the first cycle that stores sensitive files (NFR-024). Files are removed first; if that fails, the record is kept so the user can retry.
- **Supporting choices:** `Scan.user` uses `PROTECT` so deleting a user can't strand files on disk; scans are **not** registered in the Django admin, which would otherwise let staff browse every user's inventory (a bypass of D-009) and delete rows without removing files.

### D-020 · Folder upload through the browser
- **Decision:** folders are uploaded with the browser's folder picker, sending each file's relative path. The server never reads the local filesystem in this cycle. Server-side folder/repository scanning, exclusion rules, and ZIP extraction belong to Cycle 8.

---

## Cycle 4 — Text Extraction

### D-021 · Segments, and extracted text is never stored
- **Decision:** every extractor yields `Segment(text, location)` with a location such as `{"line": 12}`, `{"page": 3}`, `{"sheet": "Payroll", "cell": "C7", "header": "Contact"}` or `{"slide": 2, "part": "notes"}`. Text goes to a consumer (Cycle 5's detectors) and is never written to the database or disk; only status, counts and fixed-wording notes are kept (FR-115, FR-030).
- **Why:** detectors stay independent of file formats (SRS 6.2, principle 2), and a privacy tool shouldn't create a second copy of the sensitive content it scans.
- **For learning and debugging:** `python -m privguard_engine.extractors <local file>` prints segments for a local file.

### D-022 · Extraction dependencies
- **Installed:** `openpyxl` 3.1.5 (MIT; streaming read-only mode, formulas as written, hidden sheets included), `defusedxml` 0.7.1 (PSF; openpyxl switches both `iterparse` and `fromstring` to it automatically, verified in its source), `pypdfium2` 5.14.0 (BSD-3/Apache-2.0; PDFium). pypdfium2's 18 bundled notices were reviewed: all permissive; the only GPL text covers ICU's Autoconf build scripts, not the shipped binary. The notices must travel with any redistributed bundle (Cycle 12).
- **Not installed:** `python-docx` (needs `lxml`, and its paragraph text omits tracked deletions), `pdfplumber` (depends on `pypdfium2` plus `pdfminer.six` and Pillow), `pypdf` (a second PDF library alongside `pypdfium2`), `pandas` (no dataframes needed; NumPy on an 8 GB machine), `charset-normalizer` (BOM → strict UTF-8 → Windows-1252 suffices).

### D-023 · Our own OOXML reader for DOCX and PPTX
- **Decision:** read Office XML parts directly with `zipfile` + `defusedxml` (DTDs forbidden). DOCX: body, tables, headers, footers, footnotes, endnotes, comments and their authors, **tracked deletions**, **field codes**, document properties. PPTX: slides in **presentation order** and **speaker notes**.
- **Why:** captures text Word or PowerPoint doesn't display but the file still contains (FR-099), makes PPTX (FR-026) nearly free, avoids `lxml`, and builds the XML knowledge Cycle 10 needs for DOCX redaction.
- **Defences:** declared ZIP sizes and compression ratios are checked before anything is decompressed; reads are byte-counted; "Strict Open XML" documents are reported as not supported rather than silently empty.

### D-024 · Formats are read as lines, not parsed
- **Decision:** JSON, YAML, XML, configuration and code are extracted line by line. CSV is parsed (cells, headers and starting line numbers); XLSX cells are read through openpyxl.
- **Why:** a parser is attack surface (unsafe YAML loaders, XML entities), and line numbers stay exactly what an editor shows. Structure-aware context can be added if Cycle 5–6 detection needs it.

### D-025 · No invisible characters in source code
- **Decision:** source files must not contain literal bidirectional-override or zero-width characters; code that needs one writes an escape such as `\u202e`. Enforced by `tests/engine/test_source_hygiene.py`, which also checks that its own scanner can catch a planted character.
- **Why:** "Trojan Source" (CVE-2021-42574): such characters make code display differently from how it runs. One slipped into a Cycle 3 test through a tool's escape handling and was fixed in Cycle 4.

---

## Known temporary workarounds

### W-001 · `frontend/.npmrc` points npm at Git Bash
- **Problem:** The project path contains `&`, which `cmd.exe` treats as a command separator, so npm scripts fail.
- **Workaround:** `script-shell` set to Git Bash in a gitignored `frontend/.npmrc`.
- **Proper fix:** Rename the project folder to a path without `&` or spaces, then delete `.npmrc`. Not committed, because it hardcodes a Windows path and would break Linux development (NFR-043).
