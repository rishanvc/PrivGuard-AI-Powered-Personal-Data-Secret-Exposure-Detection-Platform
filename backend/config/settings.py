"""
Django settings for PrivGuard.

Every environment-specific or secret value is read from the environment
(SRS 13.2, NFR-016). Nothing sensitive is hardcoded here, so this file is
safe to commit.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

# ---------------------------------------------------------------- core

SECRET_KEY = env("DJANGO_SECRET_KEY")

# NFR-015: debug must be OFF unless explicitly enabled. Defaulting to False
# means a missing/!typo'd env var fails safe instead of exposing tracebacks.
DEBUG = env.bool("DJANGO_DEBUG", default=False)

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# ---------------------------------------------------------------- apps

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third party
    "rest_framework",
    "corsheaders",
    # PrivGuard
    "apps.accounts",
    "apps.scans",
    "apps.core",
]

MIDDLEWARE = [
    # CorsMiddleware must sit as high as possible, and definitely before
    # CommonMiddleware, so CORS headers are attached even to redirects/errors.
    "corsheaders.middleware.CorsMiddleware",
    # Rejects oversized uploads from the Content-Length header BEFORE anything
    # reads the body. Placed after CorsMiddleware so the 413 response still
    # carries CORS headers - otherwise the browser would hide it behind a
    # generic network error.
    "apps.core.middleware.RequestSizeLimitMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------- database

# env.db() parses DATABASE_URL into Django's DATABASES dict (SRS 7).
DATABASES = {"default": env.db("DATABASE_URL")}

# FR-004: roles live on a custom user model. This MUST be set before the very
# first migrate - swapping AUTH_USER_MODEL afterwards is a painful rebuild.
AUTH_USER_MODEL = "accounts.User"

# SRS 5.1.1: log in with username OR email. Subclasses ModelBackend, so
# Django admin login and the timing-attack mitigation keep working.
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.EmailOrUsernameBackend"]

# FR-001 / FR-007: self-registration is OFF by default (local single-user
# mode). Accounts are created with createsuperuser or the Django admin.
ALLOW_REGISTRATION = env.bool("ALLOW_REGISTRATION", default=False)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------- auth

# FR-003: Django's PBKDF2 hashing. Plain-text passwords are never stored.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------- DRF

REST_FRAMEWORK = {
    # NFR-007: deny by default. Every endpoint requires authentication unless it
    # explicitly opts out (e.g. the health check). Forgetting to add a permission
    # class therefore locks an endpoint down rather than opening it up.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # Cycle 2 decision: session cookies, not tokens. The session cookie is
    # HttpOnly, so even an XSS bug in a rendered findings preview cannot read
    # it - a token in localStorage could be stolen. See docs/decisions.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Brute-force protection for login/registration (ScopedRateThrottle).
    # Counters live in the default cache, which is per-process: correct for
    # local mode, but multi-worker deployments need a shared cache (Cycle 12).
    "DEFAULT_THROTTLE_RATES": {
        "auth": env("AUTH_THROTTLE_RATE", default="5/min"),
    },
    # FR-088: paginate large result sets.
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}

# ---------------------------------------------------------------- CORS

# NFR-017. Explicit allow-list only - never CORS_ALLOW_ALL_ORIGINS.
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------- sessions & CSRF

# FR-006. HttpOnly: JavaScript can never read the session cookie.
# SameSite=Lax: sent on same-site requests (localhost:5173 -> localhost:8000
# counts as same-site; ports don't matter), withheld on cross-site POSTs.
SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE_SECONDS", default=8 * 60 * 60)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# The SPA runs on a different origin (port) from the API, so Django's CSRF
# Origin-header check must trust it explicitly.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=CORS_ALLOWED_ORIGINS)

# ---------------------------------------------------------------- storage

# NFR-023: all mutable scan artifacts under one controlled root, which makes
# retention deletion (FR-114) a single subtree operation. Gitignored.
VAR_ROOT = Path(env("PRIVGUARD_VAR_ROOT", default="var"))
if not VAR_ROOT.is_absolute():
    VAR_ROOT = BASE_DIR / VAR_ROOT

UPLOAD_ROOT = VAR_ROOT / "uploads"
EXTRACTED_ROOT = VAR_ROOT / "extracted"
REDACTED_ROOT = VAR_ROOT / "redacted"
REPORT_ROOT = VAR_ROOT / "reports"
TMP_ROOT = VAR_ROOT / "tmp"

# Uploads do NOT use MEDIA_ROOT. They live in apps.scans.storage, a private
# storage with no URL at all. A common tutorial line -
#     urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
# - would otherwise publish every uploaded file on the web. MEDIA_ROOT points
# at an unused folder inside var/ so nothing stray lands in the project tree.
MEDIA_ROOT = VAR_ROOT / "media"
MEDIA_URL = "/media/"
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ---------------------------------------------------------------- scan limits

# FR-019, NFR-003, NFR-010. Three layers, each enforced at a different point:
#   MAX_TOTAL_SCAN_SIZE_MB  whole request -> 413 from RequestSizeLimitMiddleware,
#                                            before the body is read
#   MAX_FILES_PER_SCAN      file count    -> 400 from Django's multipart parser
#   MAX_UPLOAD_SIZE_MB      each file     -> that file is rejected; the rest continue
MAX_UPLOAD_SIZE_MB = env.int("MAX_UPLOAD_SIZE_MB", default=25)
MAX_TOTAL_SCAN_SIZE_MB = env.int("MAX_TOTAL_SCAN_SIZE_MB", default=200)
MAX_FILES_PER_SCAN = env.int("MAX_FILES_PER_SCAN", default=200)
SCAN_RETENTION_DAYS = env.int("SCAN_RETENTION_DAYS", default=30)

DATA_UPLOAD_MAX_NUMBER_FILES = MAX_FILES_PER_SCAN

# Cycle 1 correction: this setting does NOT limit file uploads. Django applies
# it only to ordinary form fields and JSON bodies (verified in
# django/http/multipartparser.py - the check sits inside `if item_type == FIELD`).
# File sizes are enforced by the three layers above. Django's default is kept.
DATA_UPLOAD_MAX_MEMORY_SIZE = 2_621_440  # 2.5 MB

# Uploads larger than this spool to a temporary file instead of memory. Those
# temp files hold sensitive content, so they go in var/tmp rather than the
# system-wide temp folder (NFR-023). Permissions apply on Linux; on Windows the
# folder's ACLs govern access.
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_TEMP_DIR = str(TMP_ROOT)
FILE_UPLOAD_PERMISSIONS = 0o600
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o700

# ---------------------------------------------------------------- scan worker (Cycle 4)

# Reading one file may take at most this long. The isolated child process is
# then killed and the file marked failed (SRS 15: "bounded processing, timeouts").
EXTRACTION_TIMEOUT_SECONDS = env.int("EXTRACTION_TIMEOUT_SECONDS", default=120)

# Per-file extraction caps (NFR-003). Reaching one marks the file "partial".
EXTRACTION_MAX_CHARS = env.int("EXTRACTION_MAX_CHARS", default=20_000_000)
EXTRACTION_MAX_PAGES = env.int("EXTRACTION_MAX_PAGES", default=2_000)
EXTRACTION_MAX_CELLS = env.int("EXTRACTION_MAX_CELLS", default=2_000_000)

WORKER_POLL_SECONDS = env.float("WORKER_POLL_SECONDS", default=2.0)  # idle: how often to look for work
WORKER_HEARTBEAT_SECONDS = 5    # "still alive", written while processing and while idle
WORKER_ALIVE_SECONDS = 30       # health check: a worker seen this recently is running
# A scan whose heartbeat is older than this was abandoned by a worker that
# died; recovery puts it back in the queue. Must comfortably exceed the
# heartbeat interval.
WORKER_STALE_SECONDS = env.int("WORKER_STALE_SECONDS", default=120)

# ---------------------------------------------------------------- detection (Cycle 5)

# Phone numbers written without a country code ("98765 43210") are read as
# numbers of this region (ISO 3166 code). Cycle 5 decision: India (D-029).
DETECTION_REGION = env("DETECTION_REGION", default="IN").upper()

# ---------------------------------------------------------------- optional components

# FR-027 / Cycle 8. Absence must degrade gracefully (NFR-032).
OCR_ENABLED = env.bool("OCR_ENABLED", default=False)
TESSERACT_CMD = env("TESSERACT_CMD", default="")

# FR-062 / Cycle 9. FR-063 + NFR-048: core scanning must work with this off.
AI_ENABLED = env.bool("AI_ENABLED", default=False)
OLLAMA_BASE_URL = env("OLLAMA_BASE_URL", default="http://localhost:11434")
OLLAMA_MODEL = env("OLLAMA_MODEL", default="qwen2.5:1.5b")

# ---------------------------------------------------------------- i18n

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

MAILERS = {
    "default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"},
}

# ---------------------------------------------------------------- production hardening

# SRS 13.3. Applied only when DEBUG is off, so local development over plain
# HTTP still works.
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
