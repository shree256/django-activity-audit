import sys
from pathlib import Path

# Add the parent directory to Python path to import activity_audit
sys.path.insert(0, str(Path(__file__).parent.parent))

DEBUG = True

SECRET_KEY = "test-secret-key-for-testing-only"

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

# Activity Audit Configuration
ACTIVITY_AUDIT_SETTINGS = {
    "LOG_LEVEL": "INFO",
    "LOG_FORMAT": "json",
    "LOG_DIR": "tests/audit",
    "ENABLE_MODEL_LOGGING": True,
    "ENABLE_REQUEST_LOGGING": True,
    "MODELS_TO_LOG": ["publications.Book", "publications.Author"],
}

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

# Create audit directory if it doesn't exist
audit_dir = Path(__file__).parent / "audit"
audit_dir.mkdir(exist_ok=True)

# Configure logging for activity audit
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "activity_audit.formatters.JsonFormatter",
        },
        "audit": {
            "()": "activity_audit.formatters.AuditFormatter",
        },
        "api": {
            "()": "activity_audit.formatters.APIFormatter",
        },
    },
    "handlers": {
        "audit_file": {
            "level": "INFO",
            "class": "activity_audit.handlers.AuditLogHandler",
            "filename": str(audit_dir / "audit.jsonl"),
            "formatter": "audit",
        },
        "api_file": {
            "level": "INFO",
            "class": "activity_audit.handlers.APILogHandler",
            "filename": str(audit_dir / "api.jsonl"),
            "formatter": "api",
        },
    },
    "loggers": {
        "audit.model": {
            "handlers": ["audit_file"],
            "level": "INFO",
            "propagate": False,
        },
        "audit.request": {
            "handlers": ["api_file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
