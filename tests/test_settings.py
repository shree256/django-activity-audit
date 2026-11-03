import sys

from pathlib import Path

# Add the parent directory to Python path to import activity_audit
sys.path.insert(0, str(Path(__file__).parent.parent))

from activity_audit.config import get_stdlib_formatter

DEBUG = True

SECRET_KEY = "test-secret-key-for-testing-only"

# Fixed so tests can assert literal hash values.
AUDIT_HASH_SECRET = "test-hash-secret"

# Use in-memory SQLite database for fast testing
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "rest_framework",
    "activity_audit",
    "tests.publications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "activity_audit.middleware.AuditLoggingMiddleware",
]

ROOT_URLCONF = "tests.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# REST Framework settings for API testing
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}


# Disable migrations for faster testing
class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = DisableMigrations()

# Test settings
TEST_RUNNER = "django.test.runner.DiscoverRunner"
USE_TZ = True
TIME_ZONE = "UTC"

# Configure logging for activity audit — structlog JSON output to the console
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structlog": get_stdlib_formatter(),
    },
    "handlers": {
        "console_struct": {
            "class": "logging.StreamHandler",
            "formatter": "structlog",
        },
    },
    "loggers": {
        "audit.model": {
            "handlers": ["console_struct"],
            "level": "INFO",
            "propagate": False,
        },
        "audit.request": {
            "handlers": ["console_struct"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
