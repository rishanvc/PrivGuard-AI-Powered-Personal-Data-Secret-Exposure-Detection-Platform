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
    # Revisited in Cycle 2 when we decide session vs token auth.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    # FR-088: paginate large result sets.
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}

# ---------------------------------------------------------------- CORS

# NFR-017. Explicit allow-list only - never CORS_ALLOW_ALL_ORIGINS.
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True

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

MEDIA_ROOT = UPLOAD_ROOT
MEDIA_URL = "/media/"
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ---------------------------------------------------------------- scan limits

# FR-019, NFR-003, NFR-010.
MAX_UPLOAD_SIZE_MB = env.int("MAX_UPLOAD_SIZE_MB", default=25)
MAX_TOTAL_SCAN_SIZE_MB = env.int("MAX_TOTAL_SCAN_SIZE_MB", default=200)
SCAN_RETENTION_DAYS = env.int("SCAN_RETENTION_DAYS", default=30)

# Reject oversized request bodies at the framework edge, before our code runs.
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # spool larger uploads to disk
DATA_UPLOAD_MAX_NUMBER_FILES = 200

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
