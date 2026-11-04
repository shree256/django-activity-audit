from django.apps import AppConfig


class AuditLoggingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "activity_audit"
    verbose_name = "Django Activity Audit"

    def ready(self):
        from . import (
            logger_levels,
            signals,  # noqa
            unregistered,  # noqa
        )
        from .config import configure
        from .shared_processors import check_settings

        check_settings()
        configure()
