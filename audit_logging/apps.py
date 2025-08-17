from django.apps import AppConfig


class AuditLoggingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "audit_logging"
    verbose_name = "Audit Logging"

    def ready(self):
        # Import and register custom log levels
        from . import logger_levels

        # Force registration of custom levels
        logger_levels.AUDIT
        logger_levels.API
        logger_levels.LOGIN

        # Initialize signals
        from . import signals  # noqa
