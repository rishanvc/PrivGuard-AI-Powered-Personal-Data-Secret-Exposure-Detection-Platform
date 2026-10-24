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
  *Resolved in Cycle 4 by D-026: PrivGuard's own worker uses the Scan table as its queue, rather than a task-framework backend.*

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
- **One exception since Cycle 5:** a finding's masked preview, at most 40 characters either side of it (D-032).

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

### D-026 · Our own worker, with extraction in an isolated child process
- **Decision:** `manage.py run_worker` uses the Scan table as its queue (`status='queued'`), claiming with `SELECT ... FOR UPDATE SKIP LOCKED`. Each file is extracted in a supervised child process that imports only `privguard_engine` (no Django); the child is reused file after file and killed after `EXTRACTION_TIMEOUT_SECONDS` (default 120).
- **Why our own worker:** one source of truth for scan state. A task-framework backend (django-tasks) would keep a second state machine beside `Scan.status`, and provides neither timeouts nor crash isolation. Celery and Redis were ruled out at the start (RAM, Windows support).
- **Why a child process:** Python cannot stop a thread stuck in C code (PDFium), so a real timeout needs a killable process; a crash in the parser takes down only the child. D-002's engine boundary is what makes the child small and Django-free.
- **Reliability rules:** a heartbeat every 5 s while processing; a scan without one for `WORKER_STALE_SECONDS` is recovered, with the file that was mid-processing marked failed so a "poison" file cannot crash workers forever; Ctrl+C puts the current file back to pending with no penalty (the child ignores Ctrl+C, so the parent decides); cancellation is noticed within about a second, even mid-file; the final status is written by compare-and-swap so it never overwrites a cancel; `delete_scan` holds a row lock so a worker can't claim a scan mid-deletion.
- **Secrets stay out of the child:** a spawned child inherits the parent's environment, which under Django includes `DATABASE_URL` and `DJANGO_SECRET_KEY` loaded from `.env`. Every child therefore starts by deleting secret-looking variables before any parsing begins, so a parser exploited by a hostile file finds no credentials to steal. Found while writing the Cycle 4 review; verified with a probe child and a mutation test.
- **Replies:** changed from pickle to checked JSON in Cycle 5 (D-035).
- **Known gaps:** an abruptly killed worker can leave a child that was *busy* at the time (an idle one exits within a fraction of a second, verified); a Windows Job Object would close this (Cycle 12). Two simultaneous workers are safe by design but not tested concurrently. The child still runs with the user's file-system permissions; OS-level sandboxing is Cycle 12 hardening.

### D-027 · `total_findings` is NULL until something searches
- **Decision:** `Scan.total_findings` is nullable; NULL means "not searched". A migration step sets it to NULL on scans created before Cycle 4.
- **Why:** 0 would claim "searched, found nothing" for scans no detector has seen, the same principle as the dashboard's "—" (Cycle 3).

---

## Cycle 5 — Personal Data Detection

### D-028 · People's names come from context rules, not a machine-learning model
- **Decision:** a name is reported only where something labels it: a name column (exact header match against an allowlist), a label such as "Customer Name:", a salutation ("Dear …"), a title (Mr, Smt, Dr …), or a document's author fields. No NER model.
- **Why:** an ML model means a download, RAM, a licence check and slower scans, and it guesses — "Rose" and "Jordan" are also flowers and countries. Context rules are explainable (FR-039) and fast.
- **Cost, measured:** on the synthetic corpus, person_name recall is 1.00 for labelled names but **0.69 including known gaps**. Not found: names in free prose ("Please call Priya Sharma"), signatures ("Signed: …"), table layouts with no colon, and a DOCX table whose label sits in the neighbouring cell. Every gap stays in `tests/engine/detection_corpus.py` so the figure can't quietly improve. An optional model can be reconsidered later; the rules would remain the fallback.
- **Names end where the next field begins:** forms and PDF text run fields together ("Customer Name: Neha Gupta Order ID: 4421"), so a name is cut at a field word such as "Order", "Phone" or "Ref". Found by probing after the corpus scored perfectly.

### D-029 · Phone numbers: `phonenumberslite`, region India
- **Decision:** `phonenumberslite` 9.0.41 (Apache-2.0), Google's libphonenumber in pure Python, validates every candidate against the numbering plan of its country. Numbers without a country code are read as Indian (`DetectionConfig.region = "IN"`).
- **Bare digit runs need a label:** every 10-digit number starting 6–9 is a *valid* Indian mobile number, and just as likely an invoice or order ID. An unformatted run with no label ("Mobile", "Ph", or a phone column) is not reported.
- **Not used:** the full `phonenumbers` package (adds geocoding, carrier and timezone data we don't need).

### D-030 · Aadhaar and PAN
- **Aadhaar:** 12 digits, first digit 2–9, with a valid **Verhoeff** check digit, *and* either Aadhaar's 4-4-4 grouping or a label. A bare, unlabelled 12-digit number is skipped: one in ten random numbers passes the checksum. Never matched inside a longer number such as a card.
- **PAN:** format only, including the holder-type letter. PAN's last character is a check character, but its algorithm is not public, so the explanation says only the format was verified.

### D-031 · Confidence is a fixed number per rule, and the method is always shown
- **Decision:** each rule has a fixed confidence (for example a labelled phone number 0.95, an unlabelled formatted one 0.8, a documentation-domain email 0.4) and records its method: `pattern`, `pattern + validation`, `pattern + checksum` or `context` (FR-039).
- **Why:** these numbers rank findings; they are not probabilities and are never presented as AI certainty. `DETECTION_VERSION` is bumped when rules change, so each scan can record which rules searched it.

### D-032 · Masking, previews and grouping — raw values never leave the child
- **Raw values exist only inside the extraction child process.** `FindingCollector` turns detections into masked `Finding`s there; only those cross to the worker.
- **Masks:** email `p***@domain` (the domain helps triage), phone keeps the country code and last two digits, Aadhaar `XXXX XXXX 1234` (UIDAI's own convention), PAN keeps its last four characters, names keep initials, dates keep only separators. **Categorical values** (gender, blood group, religion or caste, marital status, nationality) are hidden completely as `****`: one letter, or even the length, would give them away.
- **Previews (FR-085):** cut from a copy of the segment in which *every* detection is masked and every leftover run of four or more digits is replaced with `*`, so a preview never shows a neighbouring value or an unrecognised number. A preview is the one deliberate exception to D-021 ("extracted text is never stored"): at most 40 characters either side of a finding, masked. Masked values are capped at 100 characters, which also bounds every preview.
- **Known limit:** a value *no rule detects*, such as a name in prose, is not masked and can appear in a neighbour's 40-character preview. Masking can only hide what detection found.
- **Grouping:** one finding per value, per type, per file (repeats counted as `occurrences`; up to 20 distinct locations). The finding shows its *most confident* occurrence, so its explanation always describes the preview beside it. A file with more than 5,000 distinct findings is marked `truncated`, never cut silently.
- **Proven, not assumed:** tests check every corpus finding for the raw values it was built from, and seven deliberate breakages of these safeguards were each caught by a test.

### D-033 · A column's header is used for detection but never stored
- **Decision:** stored locations keep sheet, cell, row, column, line, page, slide, part, paragraph, kind, field and hidden, but not `header`.
- **Why:** in a CSV with no header row, the "header" is really the first row of data — possibly a real name or email — which would otherwise be stored unmasked beside every finding in that column (FR-115). Sheet names are kept: a finding must be locatable, and they describe the file's structure as its author named it.

### D-034 · Detection stays linear on hostile input
- **Measured before wiring detection into the worker:** every detector was timed on 1 MB single-line inputs built to be worst cases. Two quadratic paths were found and fixed: name trimming copied the rest of the line for every candidate, and overlap resolution compared every detection with every other — one hostile line yields ~166,000 detections, which would have taken about 11 minutes. Overlaps are now resolved with a byte-per-character "taken" map.
- **Result:** the whole pipeline (detectors, overlaps, masking, grouping) costs at most about 5 s per MB, on dense phone-number text, where the phone library validates every candidate; ordinary text about 0.5 s per MB. A test checks that 200,000 detections resolve in under 5 seconds.
- **Backstop:** the 120 s per-file timeout (D-026) still applies to extraction and detection together.
- **Found on the way:** a blank form ("First Name: Last Name: Email:") reported "Last" and "Email" as names. A value that is itself a label is now never a name.

### D-035 · The child replies in checked JSON, never pickle
- **Problem:** Cycle 4's child returned results with `Connection.send()`, which pickles. Unpickling can run any code the data names, so a child taken over by a hostile file could take over the worker — which holds the database credentials — through its reply.
- **Decision:** jobs still go *to* the child as pickle (the parent is trusted); replies come *back* as JSON, at most 64 MB, and `decode_reply()` checks every field — types, lengths, allowed finding types, methods and location keys, confidence between 0 and 1, at most 5,000 findings — before anything is used. A reply that fails is treated as a crash and the child is replaced.
- **Honest scope:** until the child is sandboxed (Cycle 12), a child that has been taken over can still read files the user can read, `.env` included. This closes the path into the worker's memory now; the sandbox closes the rest.
- **Bugs are ours, not the file's:** an exception in a detector becomes an `ERROR` outcome carrying only the exception type and code location (its message could quote the file). The file is marked failed with fixed wording saying the file itself may be fine; the child stays alive.

### D-036 · Storing findings
- **Model:** `Finding` follows SRS 7.2.4 field for field (`category`, `subcategory`, `detection_method`, `masked_value`, `source_location`, `context_preview`, `description`, `review_status`…). Additions: `other_locations` and `occurrences` (repeats in a file are one finding, FR-078) and `detection_version` (which rules found it, SRS 7.3). `severity` stays NULL until Cycle 6; `risk_score` and `remediation` until Cycle 7. Database constraints keep confidence within 0–1 and occurrences at 1 or more.
- **When a file counts as searched:** only if some of its text was read. A file nobody could read keeps `detection_stats` NULL, and a scan's `total_findings` stays NULL until at least one file has really been searched (D-027). The total is refreshed after every file, so it grows while a scan runs.
- **All or nothing:** a file's result and its findings are written in one transaction, by compare-and-swap on the file's `processing` status — a late result for a file that recovery already gave up on is dropped, never stored twice.
- **Scan configuration** records `detection_version`, the detectors that ran and the phone region (`DETECTION_REGION`, default `IN`), so a scan states which rules searched it.

---

## Cycle 6 — Secret and Financial Detection

### D-037 · Secrets: our own curated rules, never verified
- **Decision (Cycle 6, by the project owner):** our own rules rather than Gitleaks (a separate Go program per OS that sees raw files, not our extracted text, so secrets inside DOCX, XLSX and PDF would lose their locations) or detect-secrets (noisy keyword and entropy plugins, extra dependencies, and an optional "verify" feature that contacts services). No new dependency: `base64`, `json`, `math` and `re` from the standard library.
- **Evidence, strongest first:** structure (private-key blocks; JWTs whose parts decode to JSON; connection strings with a password; HTTP Basic headers that decode to `user:password`), then about 20 published token formats (AWS, Azure, GitHub, GitLab, Slack, Stripe, Google, OpenAI, Anthropic, Hugging Face, npm, PyPI, SendGrid, Telegram, DigitalOcean, Shopify), then values assigned to settings whose names say they hold a secret, then randomness.
- **The file type matters:** in `.env`, YAML, JSON, XML and config files an unquoted value *is* the value; in code it is an expression (`password = get_password()`), so only string literals count; in prose and documents only a password-shaped value counts ("Password: reset" is a word). A spreadsheet column headed "Password" supplies the context, as name columns do (D-028).
- **Placeholders are the main false alarm**, and are skipped: `changeme`, `replace-me…`, `${VAR}`, `$VAR`, `%VAR%`, `<your-key>`, `{{ var }}`, `ENC(…)`, file paths, environment lookups. So are settings that *describe* a secret (`TOKEN_EXPIRY_SECONDS`, `PASSWORD_MIN_LENGTH`, `SECRET_NAME`), CSRF tokens and public keys. PrivGuard's own `.env.example` is a test: it must produce no findings.
- **Entropy (FR-054) is weak evidence:** only for values in config files or string literals, never for settings that are random by design (hashes, IDs, nonces), confidence 0.4. The threshold, 2.88 + 0.27 × log₂(length) bits per character, was **measured**: it sits just above what camelCase identifiers score (99th percentile, 20,000 samples per length). Random keys clear it about 98% of the time at 32 characters and almost always beyond; at 20 characters keys and identifiers overlap, and about half of short keys are missed. One unlucky 32-character key stays in the corpus as a known gap.
- **Masks say what, never the content:** `ghp_****`, `AKIA****`, `postgres://****:****@host:5432`, `eyJ****.eyJ****.****`, `-----BEGIN RSA PRIVATE KEY----- (contents not shown)`, and `********` for passwords — not even their length. A private key's detection spans its whole block, so no preview can show its body; previews also hide any long random-looking token no rule claimed (extending D-032).
- **FR-055, enforced by a test:** no detector module imports a network library, so the detection code cannot test a credential against its service even by mistake. Every token explanation ends "Never checked against the service."
- **Known limits:** about 20 formats, where Gitleaks has about 200; a GitHub token's built-in checksum is not verified, because its exact algorithm could not be confirmed without a real token; in line-by-line files a key's body is on other lines, so all private keys of one kind in a file are grouped as one finding with each location listed.

### D-038 · Credential-shaped test data is assembled at runtime
- **Decision:** tests never contain a string in a real credential's format. `tests/engine/secret_fixtures.py` assembles each one from fragments (`"gh" + "p_" + random`) with a fixed random seed, so values are identical on every run.
- **Why:** it keeps the project rule "no secrets in source code" in letter and spirit, keeps GitHub's push protection quiet, and stops other people's secret scanners from reporting this repository as a leak.
- **Samples too:** `samples/make_secrets_finance_demo.py` is committed; the files it writes to `samples/secrets-finance-demo/` are git-ignored. Their test builds them in a temporary folder from the generator, so it runs everywhere.

### D-039 · Financial data: checksums first, labels for the rest
- **Scope (Cycle 6, by the project owner):** India, payment cards and IBAN. Payment cards, card security codes, Indian bank accounts, IFSC, UPI IDs, GSTIN, IBAN, SWIFT/BIC, transaction IDs and payment references (FR-040 to FR-043). UK sort codes and US routing numbers are out of scope; a UK account stays in the corpus as a known gap.
- **Checksums, each verified against a published example before use:** Luhn for cards (network test cards), mod-97 for IBAN (the SWIFT registry's example), Luhn mod 36 for GSTIN (the GST portal's sample `27AAPFU0939F1ZV`). Unit tests show each catches every single-character typo.
- **Cards** need Luhn, a card network's prefix *and* length, and — because 1 in 10 random numbers pass Luhn — either the usual grouping or a label, as for Aadhaar (D-030). Published test numbers (`4111 1111 1111 1111`…) are their own type, recognised even bare: they cannot be charged. **IBAN** needs its country's registry length; the candidate is cut at that length, because the pattern otherwise runs on into following capitals ("… 32 BIC CODE ON FILE"). **IFSC** needs a label or a known Indian bank's code (SBIN, HDFC…); 4 letters, a zero and 6 characters is also a product code. **UPI IDs** need a known payment app's handle or a label, and are never followed by `.com` — that would be an email address.
- **Labels without a checksum:** bank accounts (9 to 18 digits), SWIFT/BIC, security codes and transaction IDs need a label or a column header. Distinctive labels (UTR, RRN, Txn ID, payment ref) may be followed by a plain space, as bank text messages write them; SWIFT may not ("SWIFT TRANSFER"). A bare "Account" label is safe because its value must be 9 to 18 digits. Both rules were found by probing after the corpus first scored perfectly.
- **Masks (FR-045):** cards, accounts and references keep their last four digits; codes that name a bank keep the bank (`HDFC*******`, `DEUT****`, the IBAN's country); a security code shows `***`. PCI DSS forbids storing a CVV at all, which the explanation says.
- **Known limits:** card numbers written one after another with only a space between them are not found — the digits run on, which is the same boundary rule that stops a match inside a longer number. Bank account numbers have no checksum, so an unlabelled one is never found.
- **Measured:** 228-case corpus, 0 false alarms among 91 look-alikes; all financial detectors linear on 1 MB hostile inputs (at most about 4 s per MB, on IFSC-shaped text). One full timing run reported 14 s for an input it did not name; it did not recur in two further full runs or eight runs of the only randomised input, and the probe now always names its worst input.

### D-040 · Severity: one versioned table, assessed by the worker
- **Decision:** `privguard_engine/risk/severity.py` maps every kind of finding to one of FR-073's five levels, with the reason in words (FR-076): **Critical** for secrets that grant access (private keys, cloud credentials, live API tokens, connection strings with a password); **High** for passwords and other secrets, cards and security codes, bank accounts and IBANs, Aadhaar, passport, voter ID and driving licence, and special-category data (religion or caste; blood group as health data); **Medium** for PAN, phone, date of birth, address, UPI ID; **Low** for name, email, the other personal fields, IFSC, SWIFT, GSTIN, transaction IDs; **Informational** for published test cards and test-mode or documentation keys.
- **One adjustment:** weak evidence (confidence below 0.5) lowers the level by one, and the reason says so. An `example.com` email becomes Informational; a value found only by entropy becomes Medium.
- **Versioned and configurable (FR-072):** the table is one documented dictionary; `SEVERITY_POLICY_VERSION` is recorded in each scan's configuration. A test fails if a new kind of finding is added without a level.
- **Assessed by the worker, not the child:** severity is computed after `decode_reply()` has checked the reply, from the finding's validated type and confidence — a child taken over by a hostile file cannot mark its own findings harmless.
- **Not assessed is not guessed:** findings stored before Cycle 6 keep `severity` NULL, shown as "Not assessed" and sorted last; scanning again assesses them. The dashboard's "Critical / high" stays empty until something has been searched, like `total_findings` (D-027).
- **Sorting (FR-079):** `?ordering=severity` (default), `category`, `file` or `confidence`. Severity sorts by a rank computed in the database: alphabetical order would be critical, high, informational, low, medium - Medium last, below Informational. Any other value is refused with 400.
- **Not the risk score:** severity says what to fix first. The 0–100 risk score (Cycle 7) also weighs occurrences, file and context.

---

## Cycle 7 — Risk Engine and Findings UI

### D-041 · Risk: the riskiest finding, plus a little for breadth
- **Decision (Cycle 7, by the project owner):** a scan's 0–100 score is its riskiest counted finding, plus 3 for each other finding with risk 60 or more, the bonus capped at 15 and the total at 100. Never a sum (SRS 8.3): a thousand e-mail addresses score 19, Low; one private key scores 90, Critical. Rejected: the average of the top five (it averages a leaked key down) and combined probability (many small findings push it to 100, and it is hard to explain).
- **A finding's risk:** severity base (Critical 90, High 70, Medium 45, Low 20, Informational 5) × a confidence factor (0.6 + 0.4 × confidence), + up to 10 for repeats (3 × log₂ occurrences), + 5 when it sits where people rarely look — a tracked deletion, a field code, a hidden sheet, a comment, speaker notes, document properties. Worked examples: a private key at confidence 0.99 scores 90; a card number appearing twice, 72; the same card in a tracked deletion, 74.
- **Reviews (Cycle 7, by the project owner):** findings reviewed as *false positive* or *resolved* do not count. Confirmed, accepted risk and new findings do — accepted risk is still risk.
- **Honest edges:** a scan nobody could read has no score (NULL), as for `total_findings` (D-027); a scan whose remaining findings were all found before risk existed has no score either, never a claimed 0; a scan with nothing found, or everything reviewed away, scores 0 and says why.
- **Transparent (FR-076, FR-080):** every score comes with its factors in fixed wording ("Riskiest finding: Private key in deploy.pem (90)", "2 other serious finding(s), risk 60 or more: +6") and the statement that it assesses detected evidence and is not proof that files are safe or unsafe. Bands follow FR-077's default: 0–19 Low, 20–39 Moderate, 40–69 High, 70–100 Critical.
- **Versioned and tested:** `RISK_POLICY_VERSION` is recorded in each scan's configuration. Tests pin every worked example, the caps, the band edges, and that higher severity or confidence never scores lower — and that confidence strictly matters (a mutation check showed "never lower" alone also passes when confidence is ignored).
- **Efficient:** only the riskiest counted finding and the serious ones change the score, so only those rows are loaded when it is refreshed — after every file the worker finishes, and after every review.
- **Remediation (FR-084):** fixed advice per kind of finding. For secrets it always says revoke first: deleting a key does not help if the file was ever shared or committed.
- **Where it lives:** `privguard_engine/risk/` — the package planned in Cycle 1 for "severity and risk scoring". Cycle 6's `severity.py` moved into it.

### D-042 · Reviewing, searching and the audit log
- **Review (FR-086, UC-03):** `PATCH /api/findings/{id}/` accepts only `review_status`; any other field is refused with 400 rather than ignored. One transaction locks the finding, saves the status with who and when, writes the audit record and rescores the scan — all or nothing. A review that changes nothing records nothing.
- **Audit log (SRS 7.2.8; Cycle 7 decision by the project owner):** a new `audit` app, because Cycle 11 adds logins, deletions and exports to it. Records are append-only: the model refuses `save()` on an existing record and `delete()`, and its queryset refuses bulk `update()` and `delete()`, which would otherwise skip both. Metadata is limited to a list of safe keys (scan ID, kind of finding, old and new status) — anything else raises an error instead of being stored (FR-117). Records name what they describe by ID, not foreign key, so they outlive a deleted scan; the user is protected, so who did what cannot vanish with an account. **Known limit:** raw SQL could still change the table; database-level protection is Cycle 12 hardening.
- **Ownership:** a finding belongs to whoever owns its scan. `OwnedQuerysetMixin` filters on `scan__user`; `IsOwner` now follows a `__` path to the owner, keeping its explicit "None never matches" check. Another user's finding is not found (404), for administrators too (D-009). Filtering by another user's scan ID matches nothing rather than answering 404, so the filter cannot confirm that a scan exists.
- **Search and filters (FR-083, FR-087):** written by hand in `filters.py` rather than adding `django-filter`. Filters for scan, severity (including `not_assessed`), category, file type, detection method and review status take comma-separated values; every value is checked against a fixed list and an unknown one is a 400 that names the allowed values. Search covers what is stored — file paths, kinds of finding by key or label, masked values, explanations — never raw values, which were never stored. Sorting: severity (default), risk, category, file, confidence. The scan's findings tab uses the same code.
- **Dashboard (FR-081):** severity and category counts of *open* findings (not reviewed as false positive or resolved), review progress across all findings, and the five riskiest scans; "Critical / high" counts open findings only. All stay empty until something has been searched (D-027).
- **Stored and live scores agree:** a scan's detail recalculates its score live, while lists and the dashboard read the stored `risk_score` — so every review stores the new score. A mutation check found the first version of the test reading only the live score, which could not have noticed a stale stored one.

### D-043 · The findings screens
- **Filters live in the address** (`/findings?severity=critical,high&status=new&q=deploy`): a view can be bookmarked or shared, the dashboard links straight into filtered lists, and the address is the single source of truth. Search waits for a 0.3 s pause in typing.
- **Severity colours were validated, not eyeballed.** Cycle 1's palette failed a colour-vision check: medium (`#ca8a04`) and high (`#ea580c`) were nearly identical for colour-blind readers (ΔE 2.9, target 8) and close even with normal vision (11.7, floor 15). The replacement — critical `#991b1b`, high `#ea580c`, medium `#d4a017`, low `#2563eb`, info gray — passes every check (worst ΔE 8.3 colour-blind, 16.0 normal). Medium stays below 3:1 against white, so colour never carries severity alone: badges are a coloured dot beside the written level in neutral ink, bars carry their label and value.
- **Dashboard forms follow the data's job:** open findings per severity as labelled bars with the value at each tip (each row links to the filtered list); the three categories as number tiles; review progress as a meter in a neutral blue (severity colours are kept for meaning danger); the riskiest scans as a short list. Every figure is readable without hovering. Empty states say what they mean — "no scan searched yet" is not "no findings", and "no findings" is not "safe".
- **One source for thresholds:** risk bands come from the API with each score, so no page repeats the 0–19 / 20–39 / 40–69 / 70–100 numbers.
- **Reviewing:** five buttons on the finding's page, the current one pressed; the change, the last reviewer and the history appear at once. The page never offers what the API refuses.
- **Loading is derived, not stored:** each answer remembers which request it answers, and the table is "loading" when the latest request is not the one shown — the previous page stays, dimmed, instead of flashing. (Setting a loading flag inside the effect made React render twice.)
- **Not done in this cycle:** the pages were not viewed in a browser by the assistant — the user's browser test is the visual check. No new npm packages.

---

## Cycle 8 — OCR and Repository Scanning

### D-044 · OCR with Tesseract, run as a separate program
- **Decision (Cycle 8, by the project owner):** Tesseract 5.4.0 (Apache-2.0, UB Mannheim's Windows build, installed with `winget`), English only. Rejected: RapidOCR (adds onnxruntime and models to the Python environment; returns lines, not the word positions Cycle 10 needs) and leaving OCR out.
- **Optional (NFR-032):** `OCR_ENABLED` is off by default, and OCR counts as off when `TESSERACT_CMD` does not point to the program. Off, images are "not supported" and scanned pages "partly read", with the reason — never "clean". Intake, the worker and the health check all ask one function (`apps/core/ocr.py`), so they cannot disagree. The health check names the problem: disabled, program missing, or language data missing.
- **No new Python packages:** Tesseract is run with `subprocess`, not through `pytesseract` (a thin wrapper; we need our own time limits and output parsing anyway). No Pillow: an image's size is read from its PNG or JPEG header by hand, and scanned PDF pages are rendered with `pypdfium2` (already installed) and written as PGM, the simplest grayscale format Tesseract reads. Tests build their images the same way — a PNG is written with `zlib` alone, a "scanned" PDF holds only a picture of each page.
- **Images are hostile input:** the size is read from the header and refused above `OCR_MAX_MEGAPIXELS` (40) before Tesseract decodes a pixel — a decompression bomb claiming 50,000 × 50,000 never reaches it. OCR runs inside the isolated child, with one Tesseract thread, at most `OCR_MAX_PAGES` (50) scanned pages per PDF, and a time budget (`OCR_TIME_BUDGET_SECONDS`, 90, kept at least 20 s below the child's timeout). Each bound, when hit, is reported: the file is partly read — or failed, when nothing at all could be read.
- **Private temporary files (FR-030):** rendered pages show the user's documents; they are written to PrivGuard's own `var/tmp` under random names and deleted the moment Tesseract has read them, also when it fails.
- **Locations and honesty:** each line Tesseract reads is a segment with `kind: "ocr"` and its box in pixels (`ocr_box`, stored for Cycle 10's image redaction). Every finding read by OCR says so — "Read by OCR from an image, which can misread characters" — and a file whose average word confidence is below 70 gets a note that data may have been misread and missed (SRS 9.5). A misread digit usually breaks a checksum, so OCR errors tend to cause misses, not false alarms.
- **Tests do not depend on the developer's `.env`:** the scan test base pins OCR off; OCR tests switch it on explicitly, and those needing the real program are skipped where it is not installed.
- **Known limits:** Tesseract runs as a grandchild of the worker — if the extraction child is killed at its timeout, a running Tesseract can outlive it on Windows (the OCR budget ends Tesseract first in normal cases; a Job Object is Cycle 12 hardening). JPEG reading is tested with header-only files; full JPEG OCR is exercised by hand, as building a JPEG needs an image library.

---

## Known temporary workarounds

### W-001 · `frontend/.npmrc` points npm at Git Bash
- **Problem:** The project path contains `&`, which `cmd.exe` treats as a command separator, so npm scripts fail.
- **Workaround:** `script-shell` set to Git Bash in a gitignored `frontend/.npmrc`.
- **Proper fix:** Rename the project folder to a path without `&` or spaces, then delete `.npmrc`. Not committed, because it hardcodes a Windows path and would break Linux development (NFR-043).
