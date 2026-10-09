# SOFTWARE REQUIREMENTS SPECIFICATION (SRS)

## PrivGuard --- AI-Powered Personal Data & Secret Exposure Detection Platform

**Document Version:** 1.0\
**Project Type:** AI-powered privacy and security application\
**Document Status:** Initial Baseline Specification\
**Development Model:** Iterative, cycle-by-cycle development\
**Target Platform:** Web application running locally or on a self-hosted
server\
**Development Cost Target:** ₹0 --- no paid APIs or subscriptions\
**Primary Technologies:** Python, Django REST Framework, React,
PostgreSQL, local AI models\
**Intended Audience:** Developers, testers, project evaluators, and
future maintainers

------------------------------------------------------------------------

# 1. Introduction

## 1.1 Purpose

This document defines the Software Requirements Specification for
PrivGuard, an AI-powered platform designed to identify, analyze,
classify, and redact sensitive information exposed in documents,
source-code repositories, configuration files, datasets, and other
digital files.

The purpose of PrivGuard is to help individuals and organizations
identify privacy risks and accidental exposure of confidential
information before the data is shared, uploaded, committed to a
repository, or distributed.

The system will combine deterministic pattern detection, file-content
analysis, open-source security tools, OCR, and optional local AI
reasoning to produce actionable privacy and exposure reports.

This document serves as the primary reference for designing, developing,
testing, and maintaining the system.

## 1.2 Project Overview

PrivGuard is a privacy and security auditing platform that scans
user-selected files, folders, and source-code repositories to identify
potentially exposed information.

The platform will detect information such as:

-   Personal information, including names, phone numbers, email
    addresses, and addresses.
-   Financial information, including bank account details and payment
    card numbers.
-   Authentication secrets, including API keys, passwords, tokens, and
    database credentials.
-   Confidential business information, including internal URLs, employee
    records, and private configuration details.
-   Sensitive information embedded in PDFs, Word documents,
    spreadsheets, text files, source code, and supported images.

After scanning, the system will display findings, severity levels,
evidence, file locations, explanations, and recommended remediation
steps.

Users will also be able to redact sensitive information, generate
sanitized copies of supported files, and export scan reports.

## 1.3 Problem Statement

Sensitive information is frequently exposed through ordinary files,
software projects, reports, and business datasets.

Examples include:

-   Developers accidentally committing API keys to Git repositories.
-   Employees sharing spreadsheets containing personal information.
-   Organizations distributing documents containing confidential
    records.
-   Database credentials appearing in configuration files.
-   Sensitive information remaining in logs, exports, and backups.
-   Images containing personal information that is not searchable as
    ordinary text.

Manual inspection is time-consuming and can miss important exposures.

Existing security scanners may focus primarily on source-code secrets,
while ordinary document-processing tools may extract text without
evaluating privacy risks.

PrivGuard aims to combine these capabilities into one locally operated
application.

## 1.4 Objectives

The primary objectives are:

1.  Detect sensitive information in supported digital files.
2.  Identify potential credential and secret exposure.
3.  Classify findings by type, severity, and confidence.
4.  Provide evidence explaining why each finding was detected.
5.  Generate an overall risk assessment for each scan.
6.  Allow users to review and redact sensitive information.
7.  Produce downloadable sanitized files and reports.
8.  Provide optional AI-generated explanations and remediation
    recommendations.
9.  Protect scanned data by processing it locally by default.
10. Operate without paid AI APIs, cloud processing subscriptions, or
    proprietary scanning services.
11. Support scanning individual files, folders, and software
    repositories.
12. Provide a professional dashboard for reviewing and managing
    findings.

## 1.5 Scope

### In scope

-   User authentication for multi-user or self-hosted deployments.
-   File and folder upload.
-   Local directory and Git repository scanning.
-   File-type detection and text extraction.
-   Pattern-based sensitive data detection.
-   Named-entity recognition for personal information.
-   Secret and credential detection.
-   OCR for supported images and scanned documents.
-   Risk classification and prioritization.
-   Optional local LLM integration.
-   Finding review, filtering, and false-positive management.
-   Text and supported-document redaction.
-   Sanitized-file downloads.
-   PDF, CSV, and JSON report exports.
-   Scan history and dashboard analytics.
-   Audit logging and configurable data-retention rules.
-   Automated testing and local deployment.

### Out of scope for the initial release

-   Guaranteed identification of every type of fraud or data exposure.
-   Guaranteed detection of all valid or active credentials.
-   Automatic revocation of credentials or modification of external
    accounts.
-   Automatic uploading of scanned documents to external AI providers.
-   Continuous monitoring of all computer files without user
    authorization.
-   Enterprise-wide endpoint monitoring.
-   Guaranteed removal of sensitive information from every file format.
-   Automated legal or regulatory certification.
-   A guarantee that a document is safe to publish merely because no
    findings were detected.

## 1.6 Definitions and Abbreviations

  -----------------------------------------------------------------------
  Term                                Definition
  ----------------------------------- -----------------------------------
  PII                                 Personally Identifiable Information

  DLP                                 Data Loss Prevention

  LLM                                 Large Language Model

  OCR                                 Optical Character Recognition

  API                                 Application Programming Interface

  RBAC                                Role-Based Access Control

  NER                                 Named-Entity Recognition

  AST                                 Abstract Syntax Tree

  Secret                              A credential or token used to
                                      authenticate or authorize access

  Finding                             A detected or suspected
                                      sensitive-data exposure

  False positive                      A finding that does not represent a
                                      genuine exposure

  Redaction                           Removal or replacement of sensitive
                                      content

  Risk score                          A numerical indicator used to
                                      prioritize findings

  Sanitized file                      A processed copy intended to remove
                                      selected sensitive information
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 2. Overall Description

## 2.1 Product Perspective

PrivGuard will be a web-based application with a React frontend and a
Python backend.

The system will use a modular architecture so that file processing,
detection engines, risk calculation, AI explanations, and report
generation can be developed and tested independently.

The application will support two operating modes:

1.  **Local mode:** The user runs PrivGuard on their computer. Files are
    processed locally, and no external service is required for core
    detection.
2.  **Self-hosted mode:** An organization deploys PrivGuard on its own
    server and provides access to authorized users.

Local mode is the primary development and demonstration environment.

## 2.2 Product Functions

The major functions of PrivGuard are:

1.  User authentication and access control.
2.  File, folder, and repository selection.
3.  File validation and safe processing.
4.  Text extraction from supported formats.
5.  Detection of personal information.
6.  Detection of financial information.
7.  Detection of credentials and secrets.
8.  Detection of selected confidential business information.
9.  OCR-based analysis of supported images and scanned documents.
10. Finding classification and risk calculation.
11. AI-assisted explanation and remediation.
12. Finding review and false-positive management.
13. Sensitive-data redaction.
14. Sanitized-file generation and download.
15. Report generation and export.
16. Scan history and analytics.
17. Audit logging and data-retention management.

## 2.3 User Classes

### 2.3.1 Administrator

The administrator manages the application in a shared or self-hosted
deployment.

Responsibilities include:

-   Managing users and roles.
-   Configuring scanning policies.
-   Configuring file-size and resource limits.
-   Managing retention settings.
-   Viewing system health and audit logs.
-   Configuring the optional local AI model.
-   Managing supported detection rules.

In single-user local mode, the application owner may perform
administrator functions.

### 2.3.2 Security Analyst

The security analyst investigates potential exposures.

Responsibilities include:

-   Creating and running scans.
-   Reviewing findings.
-   Filtering findings by severity and category.
-   Examining evidence and context.
-   Marking findings as confirmed or false positive.
-   Generating reports.
-   Creating sanitized copies of files.

### 2.3.3 Developer

The developer scans software repositories and development artifacts.

Responsibilities include:

-   Scanning source-code directories.
-   Detecting exposed secrets and configuration credentials.
-   Identifying sensitive information in logs and data files.
-   Reviewing findings by file and line number.
-   Exporting scan results.
-   Preparing sanitized files before sharing or publishing code.

### 2.3.4 General User

The general user scans personal documents and files.

Responsibilities include:

-   Selecting files for analysis.
-   Reviewing detected personal information.
-   Masking or redacting selected values.
-   Downloading sanitized copies.
-   Viewing scan reports.

## 2.4 Operating Environment

### Minimum development environment

-   Operating system: Windows, Linux, or macOS.
-   Python 3.12 or another compatible supported version.
-   Node.js LTS.
-   PostgreSQL or an appropriately configured local development
    database.
-   A modern web browser.
-   Sufficient disk space for application files and temporary
    processing.
-   Internet access for initial installation of dependencies only, where
    needed.

### Recommended environment

-   16 GB RAM for comfortable development and optional local AI use.
-   SSD storage.
-   Additional memory or GPU resources when running larger local models.

The core scanning engine should work without a GPU. Local AI performance
will depend on available hardware and model size.

## 2.5 Design and Implementation Constraints

1.  The project must be implementable without paid services.
2.  Core detection must not depend on an external AI API.
3.  Local processing must be the default.
4.  AI model availability must not prevent ordinary scans from
    completing.
5.  Detection must be modular so new detectors can be added.
6.  The system must not expose raw sensitive values unnecessarily in the
    UI, logs, or reports.
7.  The system must not automatically transmit scanned data to external
    services.
8.  The application must not execute uploaded source code, scripts, or
    binaries.
9.  Findings must distinguish deterministic matches from heuristic or
    AI-generated conclusions.
10. Open-source dependencies must be reviewed for licensing,
    compatibility, and maintenance status before adoption.

------------------------------------------------------------------------

# 3. Functional Requirements

The following requirements define the expected behavior of the system.
Each requirement has a unique identifier for implementation and testing.

## 3.1 Module 1: Authentication and Authorization

**FR-001: User registration**\
The system shall allow account creation in deployments where
registration is enabled.

**FR-002: User login**\
The system shall authenticate users using their configured credentials.

**FR-003: Password protection**\
Passwords shall be stored using secure password hashing supported by
Django. Plain-text passwords shall never be stored.

**FR-004: User roles**\
The system shall support role-based permissions for administrators,
analysts, developers, and general users.

**FR-005: Scan ownership**\
Users shall only access scans and findings that they own or are
explicitly authorized to access.

**FR-006: Session management**\
The system shall support secure login sessions and logout.

**FR-007: Local single-user mode**\
The application shall support a local configuration suitable for one
authorized user without requiring public account registration.

## 3.2 Module 2: File and Repository Management

**FR-008: File upload**\
Users shall be able to select and upload supported files through the
frontend.

**FR-009: Multiple-file selection**\
The system shall support scanning multiple files in one scan job.

**FR-010: Folder scanning**\
The system shall support selecting a local folder through an authorized
local scanning interface or uploading a folder archive.

**FR-011: Repository scanning**\
The system shall support scanning a user-selected local Git repository.

**FR-012: File validation**\
The system shall validate file size, file type, and file structure
before processing.

**FR-013: Unsupported files**\
The system shall report unsupported file formats clearly without
silently treating them as successfully scanned.

**FR-014: Archive handling**\
The system may support ZIP archives containing supported files. It shall
reject path traversal attempts, excessive extraction sizes, and
dangerous archive structures.

**FR-015: File inventory**\
The system shall maintain an inventory of files selected for each scan.

**FR-016: Exclusion rules**\
Users shall be able to exclude selected paths, file types, or files from
a scan.

**FR-017: Duplicate handling**\
The system should avoid redundant processing of identical files within
the same scan when safe to do so.

**FR-018: Repository safety**\
The scanner shall inspect files as data and shall not execute repository
code, install repository dependencies, or run build scripts.

**FR-019: File-size limits**\
The system shall enforce configurable file-size and total-scan limits.

## 3.3 Module 3: Document Processing and Text Extraction

**FR-020: Text files**\
The system shall extract readable text from supported plain-text
formats, including TXT, LOG, JSON, YAML, XML, and configuration files.

**FR-021: Source-code files**\
The system shall process supported programming languages and
configuration files without executing them.

**FR-022: PDF extraction**\
The system shall extract text from supported text-based PDF files.

**FR-023: Scanned PDF handling**\
The system shall optionally apply OCR to scanned PDFs or pages
containing image-based content.

**FR-024: Word documents**\
The system shall extract text from supported DOCX documents.

**FR-025: Spreadsheets**\
The system shall extract cell values and relevant sheet information from
XLSX and CSV files.

**FR-026: Presentation files**\
The system may support text extraction from PPTX presentations.

**FR-027: Image OCR**\
The system shall support OCR for selected image formats, such as PNG and
JPEG, using a local OCR engine.

**FR-028: Extraction status**\
The system shall record whether extraction succeeded, partially
succeeded, failed, or was not supported.

**FR-029: Source locations**\
Where technically possible, extracted content shall retain references to
its original location, such as file path, page number, sheet name, row,
column, or line number.

**FR-030: Extraction isolation**\
Temporary extracted content shall be isolated from other users and
removed according to the configured retention policy.

## 3.4 Module 4: Personal Information Detection

**FR-031: Email detection**\
The system shall detect strings matching email-address patterns.

**FR-032: Phone detection**\
The system shall detect phone-number candidates using configurable
patterns and validation rules.

**FR-033: Address detection**\
The system shall identify potential postal addresses using patterns,
local entity-recognition models, or other configured local processing.

**FR-034: Person-name detection**\
The system shall identify likely personal names using a local
named-entity recognition model or equivalent local processing.

**FR-035: Date-of-birth candidates**\
The system shall identify potential dates of birth where contextual
information supports that classification.

**FR-036: Government identifier detection**\
The system shall support configurable detection rules for selected
government-issued or national identification formats.

**FR-037: Employee information**\
The system shall identify selected employee identifiers and
personal-record fields when supported by configured rules.

**FR-038: Context-aware classification**\
The system should use surrounding text and field names to distinguish
personal information from unrelated values.

**FR-039: Confidence reporting**\
Each finding shall include a detection confidence or a clearly
identified detection method. Rule-based matches shall not be presented
as AI certainty.

## 3.5 Module 5: Financial Information Detection

**FR-040: Payment card detection**\
The system shall detect potential payment card numbers using patterns
and appropriate validation checks, including checksum validation where
applicable.

**FR-041: Bank account detection**\
The system shall detect potential bank account numbers using
configurable patterns and context.

**FR-042: Banking codes**\
The system shall support configurable detection for banking identifiers,
including country-specific routing or branch codes where applicable.

**FR-043: Financial records**\
The system shall identify selected financial fields, such as account
holder, account number, transaction identifier, and payment reference,
when sufficient evidence exists.

**FR-044: Context-based analysis**\
The system should consider nearby labels and field names to reduce false
positives.

**FR-045: Masking**\
The system shall mask financial values in the findings list by default.

## 3.6 Module 6: Secret and Credential Detection

**FR-046: API key detection**\
The system shall detect potential API keys using configurable patterns
and known credential formats.

**FR-047: Password detection**\
The system shall identify possible passwords in configuration files,
scripts, logs, and structured data when supported by detection rules.

**FR-048: Database credentials**\
The system shall detect potential database usernames, passwords, and
connection strings.

**FR-049: Token detection**\
The system shall detect possible JWTs, access tokens, refresh tokens,
and other supported token formats.

**FR-050: Cloud credentials**\
The system shall support detection patterns for credentials associated
with supported cloud and infrastructure platforms.

**FR-051: Private-key detection**\
The system shall detect supported private-key structures and similar
credential material.

**FR-052: Environment files**\
The system shall inspect supported environment and configuration files,
including `.env` files.

**FR-053: Secret context**\
The system shall record the file path and surrounding context required
to investigate a suspected secret without unnecessarily exposing its
complete value.

**FR-054: Entropy-based detection**\
The system may use entropy or randomness heuristics to identify
potential unknown secrets.

**FR-055: Secret validation**\
The system shall not attempt to authenticate with detected credentials
or test whether credentials are active.

**FR-056: Secret severity**\
Potential credentials shall be prioritized according to the type of
secret, exposure context, and configured risk policy.

## 3.7 Module 7: Confidential Business Information Detection

**FR-057: Internal URLs**\
The system shall identify potentially internal URLs and hostnames using
configurable patterns and contextual rules.

**FR-058: Infrastructure information**\
The system shall identify selected IP addresses, service endpoints,
database hosts, and infrastructure configuration values.

**FR-059: Confidential labels**\
The system shall detect configured labels such as "Confidential,"
"Internal Use Only," or "Restricted."

**FR-060: Custom detection rules**\
Authorized users shall be able to configure custom patterns and field
names for organization-specific sensitive information.

**FR-061: Business context**\
The system should use surrounding content to distinguish potentially
sensitive internal information from ordinary public information.

## 3.8 Module 8: AI-Assisted Analysis

**FR-062: Local AI integration**\
The system shall optionally connect to a locally running LLM through a
configurable local inference interface, such as Ollama.

**FR-063: No external AI dependency**\
Core scanning and risk reporting shall continue to work when the local
AI service is unavailable.

**FR-064: Finding explanation**\
The AI module may explain why a finding could represent a privacy or
security risk.

**FR-065: Remediation recommendations**\
The AI module may recommend appropriate remediation steps based on the
finding category and available context.

**FR-066: Context-aware classification**\
The AI module may help classify ambiguous findings when deterministic
rules are insufficient.

**FR-067: Evidence-based output**\
AI-generated explanations shall reference actual finding evidence and
source locations supplied by the detection engine.

**FR-068: AI uncertainty**\
The system shall label AI conclusions as suggestions rather than
verified facts.

**FR-069: Local model configuration**\
Authorized users shall be able to configure the selected local model and
verify whether it is available.

**FR-070: Prompt-injection resistance**\
The AI module shall treat scanned file contents as untrusted data, not
as instructions. File contents shall not be allowed to override system
policies or trigger unauthorized actions.

**FR-071: Data minimization**\
The system shall send only the minimum necessary text and context to the
local AI model. Full documents shall not be sent to the model
unnecessarily.

## 3.9 Module 9: Risk Assessment Engine

**FR-072: Finding severity**\
Every finding shall receive a severity classification based on
configurable rules.

**FR-073: Severity levels**\
The system shall support Critical, High, Medium, Low, and Informational
levels.

**FR-074: Risk factors**\
Risk calculation should consider type of sensitive information, number
of occurrences, file type and context, potential exposure consequences,
detection confidence, and relevant contextual evidence.

**FR-075: Scan-level score**\
The system shall calculate an overall scan risk score between 0 and 100.

**FR-076: Transparent calculation**\
The system shall provide an explanation of the factors contributing to
the score.

**FR-077: Score interpretation**\
The default interpretation shall be configurable. An initial policy may
classify 0--19 as Low, 20--39 as Moderate, 40--69 as High, and 70--100
as Critical.

**FR-078: Duplicate findings**\
The system should group repeated occurrences where appropriate without
hiding the individual source locations.

**FR-079: Finding prioritization**\
The system shall allow findings to be sorted by severity, category,
file, and confidence.

**FR-080: Risk limitations**\
The system shall state that a risk score is an assessment based on
detected evidence and is not proof that a file is safe or unsafe.

## 3.10 Module 10: Dashboard and Findings Management

**FR-081: Dashboard**\
The system shall display summary statistics for scans, files processed,
findings, and severity distribution.

**FR-082: Scan status**\
The system shall display scan status, including queued, processing,
completed, partially completed, failed, and cancelled where supported.

**FR-083: Findings list**\
The system shall display findings in a searchable and filterable
interface.

**FR-084: Finding details**\
Users shall be able to inspect a finding's category, severity, file
location, masked value, detection method, confidence, and recommended
remediation.

**FR-085: Context preview**\
The system shall display a limited contextual preview of the affected
content, with sensitive values masked by default.

**FR-086: Finding status**\
Users shall be able to mark findings as New, Confirmed, False Positive,
Resolved, or Accepted Risk.

**FR-087: Search and filters**\
The system shall support filters by scan, severity, category, file type,
detection method, and finding status.

**FR-088: Pagination**\
The system shall paginate large result sets.

**FR-089: Scan cancellation**\
Users shall be able to cancel eligible scans without corrupting existing
scan records.

**FR-090: Empty states and errors**\
The UI shall explain when no findings are detected, a file is
unsupported, or a scan fails.

## 3.11 Module 11: Redaction and Sanitization

**FR-091: Finding selection**\
Users shall be able to select individual findings or eligible groups of
findings for redaction.

**FR-092: Text redaction**\
The system shall support redaction of supported plain-text and
structured-text files.

**FR-093: Document redaction**\
The system shall support redaction of supported document formats when
reliable redaction is technically possible.

**FR-094: Replacement options**\
The system shall support full replacement, such as `[REDACTED]`, and
selected masking options.

**FR-095: Sanitized copies**\
The system shall create a separate sanitized copy rather than
overwriting the original by default.

**FR-096: Preview**\
The system shall show a preview of proposed redactions before generating
the sanitized file.

**FR-097: Redaction verification**\
The system shall verify that selected sensitive strings have been
removed from the output text where practical.

**FR-098: Output labeling**\
The system shall clearly label generated files as sanitized copies.

**FR-099: Redaction limitations**\
The system shall warn users when a format cannot be safely sanitized or
when embedded images, metadata, comments, tracked changes, or hidden
content may retain sensitive information.

**FR-100: Image redaction**\
The system may support visual redaction of detected regions in supported
images using OCR coordinates.

**FR-101: No unsafe guarantees**\
The system shall not claim that a file is fully sanitized unless the
supported verification checks have passed. Even then, it shall
communicate the scope of those checks.

## 3.12 Module 12: Reports and Exports

**FR-102: Scan report**\
The system shall generate a report containing scan details, file
inventory, summary statistics, findings, severity, and remediation
recommendations.

**FR-103: PDF report**\
The system shall support PDF report generation.

**FR-104: CSV export**\
The system shall support CSV export of findings.

**FR-105: JSON export**\
The system shall support structured JSON export.

**FR-106: Sensitive-value masking**\
Reports shall mask sensitive values by default.

**FR-107: Report options**\
Users shall be able to select summary or detailed reports.

**FR-108: Report metadata**\
Reports shall include a scan identifier, generation time, tool version,
and relevant scan configuration.

**FR-109: Export authorization**\
Users shall only export reports for scans they are authorized to access.

## 3.13 Module 13: Scan History and Analytics

**FR-110: Scan history**\
The system shall maintain scan records according to the configured
retention policy.

**FR-111: Historical comparison**\
The system should compare findings across scans where stable file
identifiers and suitable matching information are available.

**FR-112: Resolved findings**\
The system should identify findings that were previously detected but
are no longer present in a comparable scan.

**FR-113: Trend dashboard**\
The system should display historical trends in finding counts and
severity distribution.

**FR-114: Retention management**\
The system shall support deletion of scan records and associated stored
content according to authorized retention policies.

**FR-115: No unnecessary content retention**\
The system should store finding metadata and masked evidence rather than
full extracted document contents wherever possible.

## 3.14 Module 14: Audit and Administration

**FR-116: Audit log**\
The system shall record security-relevant actions, including login
events, scan creation, scan deletion, redaction, export, and policy
changes.

**FR-117: Log minimization**\
Audit logs shall not contain raw passwords, full credentials, complete
sensitive values, or unnecessary document content.

**FR-118: Policy configuration**\
Authorized administrators shall be able to configure supported file
types, limits, detection policies, and retention settings.

**FR-119: Health status**\
The system shall report the status of essential components, including
the backend, database, OCR engine, and optional AI service.

**FR-120: Dependency status**\
The system should display whether required local detection tools and
configured models are available.

------------------------------------------------------------------------

# 4. Use Cases

## UC-01: Scan a document

**Actor:** General User

**Preconditions:** - PrivGuard is running. - The user has access to the
application. - The selected file uses a supported format.

**Main flow:** 1. The user opens the dashboard. 2. The user selects a
file. 3. The system validates the file. 4. The user starts the scan. 5.
The system extracts the supported content. 6. Detection engines analyze
the extracted content. 7. The risk engine evaluates the findings. 8. The
scan completes. 9. The dashboard displays the results. 10. The user
reviews the findings.

**Alternative flows:** - If the file is unsupported, the system reports
the limitation. - If extraction fails, the system records a failure or
partial result. - If AI is unavailable, rule-based scanning continues.

**Postcondition:** A scan record and its available findings are saved
according to the configured retention policy.

## UC-02: Scan a source-code repository

**Actor:** Developer

**Main flow:** 1. The developer selects a local repository or supported
archive. 2. The system builds a file inventory. 3. The system excludes
configured paths and unsupported files. 4. Secret detection and other
applicable detectors scan the files. 5. The system records file paths
and line references. 6. The developer filters results by severity. 7.
The developer investigates critical findings. 8. The developer exports a
report or sanitizes eligible files.

**Postcondition:** The developer receives an actionable repository
exposure report.

## UC-03: Investigate a suspected API key

**Actor:** Security Analyst

**Main flow:** 1. The analyst opens a finding. 2. The system displays
its masked value and source location. 3. The system explains the
detection method. 4. The analyst reviews the surrounding context. 5. The
analyst marks the finding as confirmed or false positive. 6. The system
records the status change. 7. The analyst reviews the recommended
remediation.

**Postcondition:** The finding has an updated review status and an audit
record.

## UC-04: Sanitize a document

**Actor:** General User

**Main flow:** 1. The user opens a completed scan. 2. The user selects
findings for redaction. 3. The system displays a preview of the proposed
changes. 4. The user confirms the operation. 5. The system generates a
separate sanitized copy. 6. The system verifies the supported redaction
checks. 7. The user downloads the result.

**Postcondition:** A separate sanitized file is generated without
modifying the original.

## UC-05: Generate a report

**Actor:** Security Analyst

**Main flow:** 1. The analyst selects a completed scan. 2. The analyst
chooses a report format. 3. The system compiles scan metadata and
findings. 4. Sensitive values are masked by default. 5. The system
generates the report. 6. The analyst downloads the report.

**Postcondition:** A report is generated and made available to an
authorized user.

## UC-06: Obtain an AI explanation

**Actor:** Security Analyst

**Preconditions:** - The local AI integration is configured and
available.

**Main flow:** 1. The analyst opens a finding. 2. The analyst requests
an AI explanation. 3. The system prepares minimal contextual evidence.
4. The local model analyzes the supplied evidence. 5. The system
displays the explanation and remediation suggestion. 6. The analyst
evaluates the suggestion.

**Alternative flow:** If the local model is unavailable, the system
displays the rule-based explanation and reports that AI assistance is
unavailable.

**Postcondition:** An explanation is displayed without requiring a paid
AI API.

------------------------------------------------------------------------

# 5. External Interface Requirements

## 5.1 User Interface

The application shall provide a responsive web interface with the
following screens:

### 5.1.1 Login screen

-   Username or email and password fields.
-   Login action.
-   Clear validation messages.

### 5.1.2 Dashboard

-   Total scans.
-   Files processed.
-   Total findings.
-   Critical and high-severity findings.
-   Recent scans.
-   Risk distribution.
-   Scan creation action.

### 5.1.3 New Scan screen

-   File upload.
-   Folder or repository selection where supported.
-   Scan options.
-   Exclusion rules.
-   Start scan action.

### 5.1.4 Scan Progress screen

-   Current status.
-   Number of files processed.
-   Number of findings.
-   Processing errors.
-   Cancellation option when available.

### 5.1.5 Findings screen

-   Search and filtering.
-   Severity indicators.
-   Category labels.
-   Masked sensitive values.
-   Source file and location.
-   Review-status controls.

### 5.1.6 Finding Details screen

-   Finding type.
-   Severity and confidence.
-   Detection method.
-   Context preview.
-   AI explanation, when enabled.
-   Remediation guidance.
-   Review-status actions.

### 5.1.7 Redaction screen

-   Finding selection.
-   Replacement options.
-   Preview of changes.
-   Generate sanitized copy action.
-   Verification status.

### 5.1.8 Reports screen

-   Report summary.
-   Export format selection.
-   Masking options.
-   Download action.

### 5.1.9 Settings screen

-   Scan limits.
-   Supported file types.
-   Detection policies.
-   AI configuration.
-   Retention settings.
-   User and role management where applicable.

## 5.2 Software Interfaces

### Frontend

-   React.
-   Vite.
-   Tailwind CSS.
-   React Router.
-   A chart library such as Recharts.

### Backend

-   Python.
-   Django.
-   Django REST Framework.
-   Background task processing where needed.

### Database

-   PostgreSQL for persistent application data.

### File-processing libraries

-   PyMuPDF for PDF text extraction.
-   python-docx for DOCX processing.
-   openpyxl and pandas for spreadsheet processing.
-   Python standard libraries for text and structured data.
-   Tesseract OCR or another suitable local OCR engine.

### Detection libraries

-   Custom Python regular expressions and validators.
-   Presidio and its compatible local recognizers, where appropriate.
-   Gitleaks or another suitable open-source secret scanner, subject to
    licensing and integration review.
-   Local named-entity recognition models when configured.

### AI interface

-   Ollama or another local inference runtime.
-   A compatible locally downloaded model.

These are implementation choices, not a requirement to use every listed
library. The development team shall select compatible versions and
verify licensing before adoption.

## 5.3 Communication Interfaces

-   The React frontend shall communicate with the backend through HTTP
    APIs.
-   Local deployments shall bind services to localhost by default where
    feasible.
-   Remote self-hosted deployments shall use HTTPS.
-   The application shall not send scanned data to external services
    unless an explicit future feature is separately designed and
    enabled.

------------------------------------------------------------------------

# 6. System Architecture

## 6.1 High-Level Architecture

The application shall use a modular architecture.

``` text
┌─────────────────────────────────────────┐
│              React Frontend             │
│ Dashboard | Scans | Findings | Reports  │
└────────────────────┬────────────────────┘
                     │ REST API
┌────────────────────▼────────────────────┐
│           Django REST Framework         │
│ Authentication | Scan API | Permissions│
└────────────────────┬────────────────────┘
                     │
┌────────────────────▼────────────────────┐
│             Scan Orchestrator           │
│ Validation | Queue | Status | Progress  │
└────────────────────┬────────────────────┘
                     │
        ┌────────────┼─────────────┐
        ▼            ▼             ▼
┌─────────────┐ ┌──────────┐ ┌──────────────┐
│ File        │ │ Detection│ │ OCR Engine   │
│ Extraction  │ │ Engines  │ │              │
└──────┬──────┘ └────┬─────┘ └──────┬───────┘
       └─────────────┼───────────────┘
                     ▼
┌─────────────────────────────────────────┐
│            Finding Aggregator            │
│ Deduplication | Context | Confidence    │
└────────────────────┬────────────────────┘
                     ▼
┌─────────────────────────────────────────┐
│              Risk Engine                │
│ Severity | Scoring | Prioritization     │
└────────────────────┬────────────────────┘
                     ▼
┌─────────────────────────────────────────┐
│          Optional Local AI Layer         │
│ Explanations | Classification | Advice  │
└────────────────────┬────────────────────┘
                     ▼
┌─────────────────────────────────────────┐
│ PostgreSQL | Reports | Sanitized Files  │
└─────────────────────────────────────────┘
```

## 6.2 Architectural Principles

1.  Detection must be independent of the AI layer.
2.  File extraction must be independent of individual detection rules.
3.  Each detector must return findings in a common format.
4.  The risk engine must use transparent, testable rules.
5.  The AI layer must not independently modify files.
6.  Redaction must be a separate, user-confirmed operation.
7.  All sensitive processing must follow the configured data-retention
    policy.
8.  The architecture must support adding new detectors without rewriting
    the application.

## 6.3 Scan Processing Workflow

1.  A user creates a scan.
2.  The backend validates permissions and scan options.
3.  The system inventories the selected files.
4.  Each file is checked against size and format limits.
5.  The extraction engine extracts text and source locations.
6.  Relevant detection engines analyze the content.
7.  Findings are normalized into a common data structure.
8.  Duplicate occurrences are grouped where appropriate.
9.  The risk engine assigns severity and risk values.
10. The optional AI layer provides explanations when requested or
    configured.
11. Scan results are stored.
12. The frontend displays the completed report.

------------------------------------------------------------------------

# 7. Database Requirements

## 7.1 General Database Design

PostgreSQL shall store application metadata, scan history, findings,
policies, and audit records.

The database should not store entire source files or full extracted
document text unless a specific feature requires it.

Sensitive values should be masked or omitted from persisted records by
default.

## 7.2 Main Entities

### 7.2.1 User

Fields:

-   `id`
-   `username`
-   `email`
-   `password`
-   `role`
-   `is_active`
-   `created_at`
-   `updated_at`

The password field shall use Django's secure password-hashing mechanism.

### 7.2.2 Scan

Fields:

-   `id`
-   `user_id`
-   `name`
-   `scan_type`
-   `status`
-   `started_at`
-   `completed_at`
-   `total_files`
-   `processed_files`
-   `failed_files`
-   `total_findings`
-   `risk_score`
-   `configuration`
-   `error_summary`
-   `created_at`

The configuration field shall store safe scan options and exclusions,
not credentials.

### 7.2.3 ScannedFile

Fields:

-   `id`
-   `scan_id`
-   `file_name`
-   `relative_path`
-   `file_type`
-   `file_size`
-   `file_hash`
-   `processing_status`
-   `extraction_status`
-   `error_summary`
-   `created_at`

The application shall avoid exposing sensitive absolute file paths
unnecessarily.

### 7.2.4 Finding

Fields:

-   `id`
-   `scan_id`
-   `scanned_file_id`
-   `category`
-   `subcategory`
-   `severity`
-   `confidence`
-   `detection_method`
-   `masked_value`
-   `source_location`
-   `context_preview`
-   `risk_score`
-   `description`
-   `remediation`
-   `review_status`
-   `created_at`
-   `updated_at`

The source-location field may contain a line number, page number,
spreadsheet coordinates, or OCR region coordinates.

### 7.2.5 DetectionRule

Fields:

-   `id`
-   `name`
-   `category`
-   `pattern_or_configuration`
-   `severity`
-   `is_enabled`
-   `version`
-   `created_at`
-   `updated_at`

Sensitive rule configuration and credentials shall be protected from
unauthorized access.

### 7.2.6 RedactionJob

Fields:

-   `id`
-   `scan_id`
-   `user_id`
-   `source_file_id`
-   `selected_finding_ids`
-   `output_file_name`
-   `status`
-   `verification_status`
-   `created_at`
-   `completed_at`
-   `error_summary`

### 7.2.7 Report

Fields:

-   `id`
-   `scan_id`
-   `user_id`
-   `format`
-   `report_path`
-   `contains_sensitive_data`
-   `created_at`
-   `expires_at`

### 7.2.8 AuditLog

Fields:

-   `id`
-   `user_id`
-   `action`
-   `resource_type`
-   `resource_id`
-   `timestamp`
-   `result`
-   `safe_metadata`

Audit records shall not contain raw credentials or complete sensitive
values.

### 7.2.9 ApplicationSettings

Fields:

-   `id`
-   `setting_key`
-   `setting_value`
-   `updated_by`
-   `updated_at`

Only authorized users shall modify protected settings. Secrets used by
the application should be stored in environment variables or another
suitable secret-management mechanism, not ordinary settings records.

## 7.3 Entity Relationships

-   One User can create many Scans.
-   One Scan can contain many ScannedFiles.
-   One Scan can contain many Findings.
-   One ScannedFile can have many Findings.
-   One Scan can produce multiple Reports.
-   One Scan can have multiple RedactionJobs.
-   One User can create multiple AuditLog entries.
-   DetectionRule records can be referenced by findings through a rule
    identifier or versioned detector metadata.

## 7.4 Database Integrity

The system shall:

-   Enforce foreign-key relationships.
-   Use transactions for operations that modify related records.
-   Index frequently queried fields, including scan identifiers,
    severity, category, and review status.
-   Apply retention and deletion policies consistently.
-   Avoid storing raw sensitive content in database indexes or logs.

------------------------------------------------------------------------

# 8. Risk Assessment and Detection Logic

## 8.1 Detection Strategy

PrivGuard shall use multiple complementary detection methods.

### Deterministic detection

Used for:

-   Email patterns.
-   Recognizable phone numbers.
-   Payment card candidates.
-   Known credential formats.
-   Private-key markers.
-   Structured fields and configuration patterns.

### Context-aware detection

Used for:

-   Person names.
-   Addresses.
-   Date-of-birth candidates.
-   Confidential business terms.
-   Ambiguous values requiring surrounding context.

### AI-assisted analysis

Used for:

-   Explaining findings.
-   Suggesting remediation.
-   Helping classify ambiguous findings.
-   Summarizing scan results.

AI shall supplement deterministic detection rather than replace it.

## 8.2 Finding Data Structure

Each finding should contain:

-   Unique finding identifier.
-   Scan identifier.
-   File identifier.
-   Category and subcategory.
-   Detection method.
-   Masked value or evidence.
-   Source location.
-   Severity.
-   Confidence where meaningful.
-   Risk score.
-   Explanation.
-   Recommended remediation.
-   Review status.

## 8.3 Risk Scoring

The system shall use a documented and testable scoring policy.

An initial implementation may calculate a weighted score based on:

-   Base severity of the finding.
-   Confidence in the detection.
-   Sensitivity of the information.
-   Context of exposure.
-   Potential impact.

The score shall be normalized to a 0--100 range.

A scan-level score may be derived from the most serious findings, their
confidence, and the distribution of findings. It should not be a simple
sum that increases without limit as more files are scanned.

The exact formula shall be defined during implementation, versioned, and
covered by automated tests.

The score is intended for prioritization. It is not a formal measure of
legal compliance or proof of exploitability.

## 8.4 False Positives and False Negatives

The system shall support:

-   Configurable detection rules.
-   Context-aware classification.
-   Finding review statuses.
-   Exclusion rules.
-   Tests using known-positive and known-negative examples.
-   Clear indications when a detector has limited coverage.

The system shall not claim complete detection of all personal
information, all credential formats, or all sensitive content.

------------------------------------------------------------------------

# 9. Redaction and Sanitization Requirements

## 9.1 General Rules

1.  Original files shall remain unchanged by default.
2.  Redaction shall operate on a separate copy.
3.  Users shall preview proposed redactions before generating output.
4.  The system shall record which findings were selected.
5.  The system shall report any redaction or verification failures.
6.  Generated files shall be stored in a controlled output directory or
    protected temporary storage.
7.  Output files shall follow retention rules.

## 9.2 Text-Based Files

For supported text-based files, the system shall replace selected
sensitive values with a configured replacement marker.

The system shall preserve unrelated content where possible.

## 9.3 Structured Files

For CSV, JSON, and other supported structured formats, the system should
preserve the format and valid structure after redaction.

Automated tests shall verify that the resulting files remain parseable.

## 9.4 PDF and Office Documents

Document redaction shall use format-specific processing.

The system shall not assume that drawing a black rectangle over text
securely removes the underlying text. Redaction must remove or
irreversibly replace the underlying content where supported.

The application shall warn users about possible residual data in:

-   Metadata.
-   Comments.
-   Revision history.
-   Embedded objects.
-   Hidden sheets or slides.
-   Embedded images.
-   Attachments or other embedded files.

If reliable sanitization cannot be performed, the application shall
report the limitation instead of claiming success.

## 9.5 Image Redaction

For supported images, the system may use OCR to locate sensitive text
and apply irreversible visual redaction to a generated copy.

The system shall report when text detection is incomplete or when OCR
confidence is insufficient.

------------------------------------------------------------------------

# 10. Non-Functional Requirements

## 10.1 Performance

**NFR-001:** The system should process ordinary text files without
unnecessary AI calls.

**NFR-002:** The system shall provide scan progress for long-running
operations.

**NFR-003:** File processing shall use configurable resource limits.

**NFR-004:** Large scans should be processed incrementally instead of
loading all file contents into memory simultaneously.

**NFR-005:** Optional AI analysis should be performed selectively to
reduce resource consumption.

**NFR-006:** Performance targets shall be established using a documented
benchmark dataset and the target computer's hardware.

## 10.2 Security

**NFR-007:** Authentication and authorization shall be enforced on
protected endpoints.

**NFR-008:** Passwords shall be securely hashed.

**NFR-009:** Uploaded files shall be treated as untrusted input.

**NFR-010:** The application shall validate file types and impose size
limits.

**NFR-011:** The application shall not execute uploaded scripts,
binaries, or source code.

**NFR-012:** File paths and archive entries shall be validated to
prevent path traversal.

**NFR-013:** Database queries shall use safe ORM operations or
parameterized queries.

**NFR-014:** Sensitive values shall be masked in the UI and reports by
default.

**NFR-015:** Debug mode shall be disabled in production deployments.

**NFR-016:** Production secrets shall be stored outside source control.

**NFR-017:** Cross-origin access and browser security settings shall be
configured appropriately.

**NFR-018:** The application shall prevent users from accessing another
user's scans, files, findings, or reports without authorization.

**NFR-019:** Logs shall avoid exposing passwords, tokens, and raw
sensitive values.

**NFR-020:** The system shall provide a clear local-only configuration
that does not require external AI connectivity.

## 10.3 Privacy

**NFR-021:** Local processing shall be the default operating mode.

**NFR-022:** The system shall not transmit scanned content to external
AI services by default.

**NFR-023:** Temporary files and generated outputs shall be stored in
controlled locations.

**NFR-024:** Users shall be able to delete scan records and associated
retained content according to the configured policy.

**NFR-025:** The application shall minimize the amount of sensitive data
persisted in the database.

**NFR-026:** The application shall clearly identify optional
integrations that may communicate outside the local environment.

**NFR-027:** Telemetry containing scanned content shall not be collected
by the core application.

## 10.4 Reliability

**NFR-028:** A failure in one file should not unnecessarily terminate an
entire multi-file scan.

**NFR-029:** The system shall record processing errors and allow users
to identify files that were not fully analyzed.

**NFR-030:** Scan status shall remain consistent after recoverable
processing failures.

**NFR-031:** Database operations shall preserve referential integrity.

**NFR-032:** The application shall handle unavailable optional AI or OCR
components gracefully.

## 10.5 Usability

**NFR-033:** The interface shall use clear labels and explanations
suitable for non-specialist users.

**NFR-034:** Findings shall be grouped and filterable.

**NFR-035:** Severity levels shall use consistent labels and visual
indicators.

**NFR-036:** Sensitive values shall be hidden by default, with access to
more detailed evidence controlled by permissions and user actions.

**NFR-037:** The interface shall provide clear feedback for uploads,
scans, errors, exports, and redaction.

## 10.6 Maintainability

**NFR-038:** Detection engines shall be implemented as independent
modules.

**NFR-039:** Detection rules shall be testable without starting the full
web application.

**NFR-040:** APIs and important data structures shall be documented.

**NFR-041:** The project shall use version control.

**NFR-042:** Automated tests shall cover core detection, access control,
risk scoring, and redaction.

## 10.7 Portability

**NFR-043:** The application shall support Windows and Linux development
environments, subject to compatible dependencies.

**NFR-044:** Deployment instructions shall document environment
variables, database setup, required models, and optional components.

**NFR-045:** The application should support containerized deployment
where practical.

## 10.8 Cost

**NFR-046:** The project shall not require paid AI APIs or subscriptions
for its core functionality.

**NFR-047:** Required dependencies shall be selected from suitable
free/open-source software with compatible licenses.

**NFR-048:** Local inference shall be optional and must not block the
rule-based scanning workflow.

**NFR-049:** No paid cloud infrastructure shall be required for local
development and demonstration.

------------------------------------------------------------------------

# 11. API Requirements

The backend shall expose REST APIs for the frontend. Exact routes may be
refined during implementation while preserving the defined
functionality.

  ----------------------------------------------------------------------------------
  Method                  Endpoint                           Purpose
  ----------------------- ---------------------------------- -----------------------
  POST                    `/api/auth/login/`                 Authenticate a user

  POST                    `/api/auth/logout/`                End the session

  GET                     `/api/dashboard/`                  Retrieve dashboard
                                                             statistics

  POST                    `/api/scans/`                      Create a scan

  GET                     `/api/scans/`                      List authorized scans

  GET                     `/api/scans/{id}/`                 Retrieve scan details

  POST                    `/api/scans/{id}/start/`           Start an eligible scan

  POST                    `/api/scans/{id}/cancel/`          Cancel an eligible scan

  GET                     `/api/scans/{id}/findings/`        Retrieve scan findings

  GET                     `/api/findings/{id}/`              Retrieve finding
                                                             details

  PATCH                   `/api/findings/{id}/`              Update finding review
                                                             status

  POST                    `/api/findings/{id}/explain/`      Request optional AI
                                                             explanation

  POST                    `/api/redactions/`                 Create a redaction job

  GET                     `/api/redactions/{id}/`            Retrieve redaction
                                                             status

  GET                     `/api/redactions/{id}/download/`   Download a sanitized
                                                             copy

  POST                    `/api/reports/`                    Generate a report

  GET                     `/api/reports/{id}/download/`      Download an authorized
                                                             report

  GET                     `/api/settings/`                   Retrieve permitted
                                                             settings

  PATCH                   `/api/settings/`                   Update authorized
                                                             settings

  GET                     `/api/health/`                     Check application
                                                             component status
  ----------------------------------------------------------------------------------

### API rules

-   Protected endpoints shall require authentication.
-   Object-level permissions shall be checked for every scan, finding,
    and file operation.
-   Uploads shall be validated before processing.
-   Long-running operations shall return a job identifier and expose
    status.
-   API responses shall not include full secret values by default.
-   Errors shall use a consistent response structure.
-   API documentation shall be maintained during development.

------------------------------------------------------------------------

# 12. Testing Requirements

## 12.1 Unit Testing

The following components shall have unit tests:

-   File-type validation.
-   Text extraction.
-   Email detection.
-   Phone detection.
-   Financial identifier detection.
-   Secret detection.
-   Context classification.
-   Finding normalization.
-   Severity assignment.
-   Risk-score calculation.
-   Redaction transformations.
-   Report generation.

## 12.2 Integration Testing

Integration tests shall verify:

-   Frontend-to-backend API communication.
-   Database persistence.
-   Multi-file scan processing.
-   Detection engine integration.
-   OCR integration.
-   Local AI integration.
-   Finding status updates.
-   Report export.
-   Sanitized-file download.
-   Scan cancellation and failure handling.

## 12.3 Security Testing

Security testing shall include:

-   Unauthorized access attempts.
-   Cross-user scan and file access attempts.
-   Malicious file uploads.
-   Archive path traversal.
-   Oversized files.
-   Invalid file structures.
-   Secret leakage through logs and API responses.
-   Prompt injection contained in scanned documents.
-   Unsafe download paths.
-   Authentication and session management.
-   Access to expired or deleted output files.

## 12.4 Detection Quality Testing

A test corpus shall include synthetic files containing known sensitive
information and negative examples that resemble sensitive data but
should not trigger findings.

The test suite shall measure:

-   Precision.
-   Recall.
-   False-positive rate.
-   False-negative rate.
-   Processing time.
-   Redaction success rate.

Sensitive test data should be synthetic. Real personal information shall
not be used without appropriate authorization and safeguards.

## 12.5 Redaction Testing

Tests shall confirm that:

-   Selected values are removed from supported text output.
-   Unselected content is preserved where expected.
-   JSON and CSV output remain valid when required.
-   PDF redaction removes underlying text for supported workflows.
-   Redaction verification identifies incomplete processing.
-   Original files remain unchanged by default.

## 12.6 User Acceptance Testing

The project shall be accepted for its initial release when the following
workflows pass:

1.  A user can start a scan and view its progress.
2.  The system detects configured sensitive patterns in supported files.
3.  The system identifies supported credential patterns in source-code
    repositories.
4.  Findings display file locations and masked evidence.
5.  The dashboard displays scan and finding summaries.
6.  The user can filter findings and update review statuses.
7.  A report can be generated and exported.
8.  Supported text files can be sanitized and downloaded.
9.  The core scanning engine operates without a running LLM.
10. No scanned content is transmitted to an external AI API by the
    default configuration.
11. Authorization checks prevent unauthorized access to another user's
    data in shared deployments.
12. Unsupported formats and processing failures are clearly reported.

------------------------------------------------------------------------

# 13. Deployment Requirements

## 13.1 Local Development

The initial development deployment shall use:

-   React/Vite frontend.
-   Django REST Framework backend.
-   PostgreSQL database.
-   Local file storage.
-   Optional local OCR.
-   Optional local LLM through Ollama.

The frontend and backend may run as separate local development services.

## 13.2 Environment Configuration

The application shall support environment-based configuration for:

-   Django secret key.
-   Database connection.
-   Debug mode.
-   Allowed hosts.
-   File-size limits.
-   Storage locations.
-   Retention settings.
-   OCR configuration.
-   Local AI endpoint and model name.

Environment files containing secrets shall not be committed to public
repositories.

An example environment file shall contain placeholder values only.

## 13.3 Production or Self-Hosted Deployment

A production deployment shall include:

-   Secure HTTPS access.
-   Restricted network exposure.
-   Appropriate authentication.
-   Database access controls.
-   Protected storage.
-   Secure environment configuration.
-   Resource limits for file processing.
-   A documented backup and recovery approach.
-   Log and retention management.

If the application is exposed to a network, additional deployment
hardening shall be performed before use with real confidential
information.

------------------------------------------------------------------------

# 14. Development Plan

The project shall be implemented incrementally. Each cycle should
produce a working, testable result.

## Cycle 1: Project Foundation

-   Define repository structure.
-   Set up Django REST Framework.
-   Set up React, Vite, and Tailwind CSS.
-   Configure PostgreSQL.
-   Add environment configuration.
-   Create the initial dashboard layout.
-   Verify frontend-backend connectivity.

**Deliverable:** A running full-stack application.

## Cycle 2: Authentication and Permissions

-   Implement login and logout.
-   Configure roles and access control.
-   Add scan ownership rules.
-   Test protected endpoints.

**Deliverable:** A secure application foundation.

## Cycle 3: File Upload and Inventory

-   Implement file upload.
-   Add file validation.
-   Create file inventory records.
-   Add size and type restrictions.
-   Implement scan status tracking.

**Deliverable:** Users can create a scan and inventory selected files.

## Cycle 4: Text Extraction

-   Add text and configuration file extraction.
-   Add PDF and DOCX support.
-   Add CSV and XLSX support.
-   Track source locations.
-   Handle extraction failures.

**Deliverable:** A reliable document-processing pipeline.

## Cycle 5: Personal Information Detection

-   Implement email and phone detection.
-   Add contextual detection.
-   Integrate local NER where appropriate.
-   Normalize findings.
-   Build unit tests.

**Deliverable:** The first functional detection engine.

## Cycle 6: Secret and Financial Detection

-   Implement credential detection.
-   Add configuration-file scanning.
-   Add supported financial patterns.
-   Add secret masking.
-   Add severity assignment.

**Deliverable:** A multi-category sensitive-data scanner.

## Cycle 7: Risk Engine and Findings UI

-   Implement risk scoring.
-   Add finding review statuses.
-   Add search and filters.
-   Add dashboard statistics.
-   Add source-context previews.

**Deliverable:** A usable privacy-audit dashboard.

## Cycle 8: OCR and Repository Scanning

-   Add local OCR.
-   Add scanned-PDF support.
-   Implement local repository scanning.
-   Add exclusions and path safety.
-   Test mixed-format scans.

**Deliverable:** Broader scanning coverage.

## Cycle 9: Local AI Integration

-   Integrate the optional local LLM.
-   Add finding explanations.
-   Add remediation recommendations.
-   Add uncertainty and evidence handling.
-   Test behavior when AI is unavailable.

**Deliverable:** AI-assisted investigation without paid APIs.

## Cycle 10: Redaction and Sanitization

-   Implement redaction preview.
-   Generate sanitized copies.
-   Add format-specific verification.
-   Protect temporary and output files.
-   Add failure warnings.

**Deliverable:** A safe redaction workflow for supported formats.

## Cycle 11: Reports and History

-   Add PDF, CSV, and JSON reports.
-   Implement scan history.
-   Add historical comparisons.
-   Add retention rules.
-   Complete audit logging.

**Deliverable:** A complete reporting and review workflow.

## Cycle 12: Security, Testing, and Release

-   Complete integration and security tests.
-   Review dependency licenses.
-   Optimize performance.
-   Document setup and limitations.
-   Add deployment configuration.
-   Prepare sample data and demonstrations.

**Deliverable:** A portfolio-ready PrivGuard release.

------------------------------------------------------------------------

# 15. Risks and Mitigation

  -----------------------------------------------------------------------
  Risk                    Impact                  Mitigation
  ----------------------- ----------------------- -----------------------
  False positives         Users may distrust      Use context,
                          findings                validation, and review
                                                  statuses

  Missed sensitive        Exposure may remain     Test multiple detectors
  information             undetected              and clearly communicate
                                                  limitations

  Limited local hardware  AI analysis may be slow Keep AI optional and
                                                  use smaller compatible
                                                  models

  OCR errors              Incorrect or missed     Report OCR status and
                          detections              use confidence
                                                  thresholds

  Malicious uploads       Security compromise     Validate files, isolate
                                                  processing, enforce
                                                  limits, and avoid
                                                  executing content

  Sensitive data stored   Secondary exposure      Mask values and
  in logs                                         minimize logged content

  Unsafe redaction        Data may remain         Use format-specific
                          recoverable             removal and
                                                  verification

  Model hallucinations    Incorrect explanations  Ground explanations in
                                                  actual findings and
                                                  label AI output as
                                                  advisory

  Dependency changes      Installation failures   Pin compatible versions
                                                  and test installation
                                                  instructions

  Licensing               Redistribution or usage Review dependency and
  incompatibility         restrictions            model licenses before
                                                  release

  Resource exhaustion     Application slowdown or Use bounded processing,
                          crash                   timeouts, and resource
                                                  limits
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 16. Assumptions and Dependencies

1.  The user has permission to scan the selected files and repositories.
2.  The development machine can run the backend, database, and frontend.
3.  Required packages and models can be installed from legitimate
    distribution sources.
4.  Local AI capabilities depend on the selected model, hardware, and
    runtime.
5.  Some detection categories require configurable country-specific
    rules.
6.  OCR quality depends on image quality, language support, and model
    configuration.
7.  Not every file format can be safely sanitized.
8.  Open-source availability does not automatically mean every model
    permits unrestricted commercial use.
9.  External integrations are not necessary for the initial release.
10. Detection and risk results are decision-support information, not
    guarantees of security or compliance.

------------------------------------------------------------------------

# 17. Acceptance Criteria

The initial release shall be considered complete when:

-   The application runs locally without paid services.
-   Users can scan supported files and repositories.
-   The system extracts text from the supported formats.
-   Personal-information, financial-information, and secret-detection
    modules produce findings for their configured test cases.
-   Findings include category, severity, detection method, masked
    evidence, and source location where available.
-   Scan-level risk scoring works according to the documented policy.
-   The dashboard displays scan results.
-   Users can filter and review findings.
-   Reports can be generated and downloaded.
-   Supported files can be sanitized without overwriting originals.
-   Optional AI explanations work with a locally configured model.
-   Scanning remains functional when the AI model is unavailable.
-   The application does not require paid API keys.
-   Default operation does not transmit scanned content to external AI
    services.
-   Core authorization, file-handling, and redaction tests pass.
-   Installation, configuration, and user instructions are documented.
-   Known limitations are clearly disclosed.

------------------------------------------------------------------------

# 18. Future Enhancements

The following features may be considered after the initial release:

1.  Pre-commit Git scanning to detect secrets before code is committed.
2.  Continuous repository scanning on a schedule.
3.  Additional programming-language and credential detectors.
4.  Local-language PII detection for Indian languages.
5.  Advanced OCR for multilingual documents.
6.  Custom organization-specific data policies.
7.  Improved detection of sensitive information in images and
    presentations.
8.  Metadata sanitization for additional file formats.
9.  A policy engine for different sensitivity levels.
10. Comparison of scan results across repository versions.
11. Optional local browser-based scanning workflows.
12. Integration with self-hosted Git platforms.
13. A plugin architecture for adding new detectors.
14. Improved model benchmarking and detection-quality dashboards.
15. Optional deployment as a self-hosted organizational privacy auditing
    service.

Any future network integrations must be separately designed with
explicit security and privacy controls.

------------------------------------------------------------------------

# 19. Conclusion

PrivGuard is intended to be a modular, privacy-focused software
application that helps users identify and reduce accidental exposure of
personal information, financial records, confidential business
information, and authentication secrets.

Its key differentiator is the combination of deterministic detection,
contextual analysis, local AI assistance, evidence-based findings, and
controlled redaction in one application.

The project is designed to be developed and demonstrated without paid
APIs or subscriptions. Core scanning shall remain functional without a
local language model, while optional AI features provide additional
explanations and recommendations.

This specification establishes the baseline requirements for
development. Detailed implementation choices, exact risk formulas,
supported formats, and model selections may be refined during
development provided that the security, privacy, cost, and functional
requirements defined here remain satisfied.

**End of Software Requirements Specification.**
