from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.db.migrations import Migration
from django.db.migrations.recorder import MigrationRecorder
from django.apps import apps

UNREGISTERED_CLASSES = [
    Migration,
    Session,
    Permission,
    ContentType,
    MigrationRecorder.Migration,
]

# Import and unregister LogEntry class only if Django Admin app is installed
if apps.is_installed("django.contrib.admin"):
    from django.contrib.admin.models import LogEntry

    UNREGISTERED_CLASSES += [LogEntry]

# URL patterns to exclude from logging
UNREGISTERED_URLS = [r"^/admin/", r"^/static/", r"^/favicon.ico$"]
UNREGISTERED_URLS = getattr(
    settings, "EASY_LOGGING_UNREGISTERED_URLS_DEFAULT", UNREGISTERED_URLS
)
UNREGISTERED_URLS.extend(getattr(settings, "EASY_LOGGING_UNREGISTERED_URLS_EXTRA", []))

# URL patterns to include in logging (if empty, all URLs are logged)
REGISTERED_URLS = getattr(settings, "EASY_LOGGING_REGISTERED_URLS", [])
