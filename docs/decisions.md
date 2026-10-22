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

## Known temporary workarounds

### W-001 · `frontend/.npmrc` points npm at Git Bash
- **Problem:** The project path contains `&`, which `cmd.exe` treats as a command separator, so npm scripts fail.
- **Workaround:** `script-shell` set to Git Bash in a gitignored `frontend/.npmrc`.
- **Proper fix:** Rename the project folder to a path without `&` or spaces, then delete `.npmrc`. Not committed, because it hardcodes a Windows path and would break Linux development (NFR-043).
