from django.apps import AppConfig


class EasyLoggingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "easy_logging"
    verbose_name = "Easy Audit Logging"

    def ready(self):
        # Import and register custom log levels
        from . import logger_levels

        # Force registration of custom levels
        logger_levels.AUDIT
        logger_levels.API
        logger_levels.LOGIN

        # Initialize signals
        from . import signals  # noqa
