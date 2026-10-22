# PrivGuard

**AI-Powered Personal Data & Secret Exposure Detection Platform**

PrivGuard scans files, folders, and source-code repositories to find sensitive
information before it gets shared, uploaded, committed, or distributed — personal
data, financial details, API keys and credentials, and confidential business
information.

Everything is processed locally by default. The platform is built to run with no
paid APIs, cloud processing subscriptions, or proprietary scanning services.

## What it detects

- **Personal information** — names, phone numbers, email addresses, addresses
- **Financial information** — bank account details, payment card numbers
- **Authentication secrets** — API keys, passwords, tokens, database credentials
- **Confidential business information** — internal URLs, employee records, private config

Supported sources include PDFs, Word documents, spreadsheets, text files, source
code, and images via OCR.

## How it works

1. **Extract** — detect file types and pull text out of documents, code, and images
2. **Detect** — deterministic pattern matching, validators, named-entity recognition,
   and open-source secret scanning
3. **Assess** — classify each finding by type, severity, and confidence, with evidence
   explaining why it was flagged
4. **Act** — review findings, mark false positives, redact sensitive values, and export
   sanitized files and reports

Findings always distinguish deterministic matches from heuristic or AI-generated
conclusions. Optional local LLM integration adds plain-language explanations and
remediation advice, but core scanning never depends on it.

## Planned stack

| Layer | Technology |
| --- | --- |
| Frontend | React, Vite, Tailwind CSS, React Router |
| Backend | Python 3.12, Django, Django REST Framework |
| Database | PostgreSQL |
| Extraction | pdfplumber / pypdf, python-docx, openpyxl, Tesseract OCR |
| Detection | Custom regex + validators, spaCy NER, Presidio, Gitleaks |
| AI (optional) | Ollama with a locally downloaded model |

The core scanning engine runs without a GPU.

## Status

Early development. The full requirements baseline lives in
[PrivGuard_SRS.md](PrivGuard_SRS.md) — 14 functional modules, use cases, interface
requirements, and non-functional requirements.

## Scope boundaries

PrivGuard is a detection aid, not a guarantee. It does not promise to catch every
exposure or every valid credential, does not revoke credentials or modify external
accounts, and never uploads scanned data to external services. No findings on a
document does not mean the document is safe to publish.

## License

MIT - see [LICENSE](LICENSE).

All runtime dependencies are selected for permissive licenses (MIT / BSD /
Apache-2.0 / MPL-2.0) so PrivGuard can stay MIT. Copyleft-licensed libraries
are not linked; AGPL alternatives such as PyMuPDF were deliberately excluded.
