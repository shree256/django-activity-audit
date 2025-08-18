from .constants import CONSOLE_FORMAT
from .logger_levels import API, AUDIT, LOGIN


def get_console_formatter() -> dict:
    return {
        "format": CONSOLE_FORMAT,
    }


def get_json_formatter() -> dict:
    return {
        "()": "django_activity_audit.formatters.JsonFormatter",
    }


def get_api_formatter() -> dict:
    return {
        "()": "django_activity_audit.formatters.APIFormatter",
    }


def get_audit_formatter() -> dict:
    return {
        "()": "django_activity_audit.formatters.AuditFormatter",
    }


def get_login_formatter() -> dict:
    return {
        "()": "django_activity_audit.formatters.LoginFormatter",
    }


def get_json_handler(
    level: str,
    filename: str = "audit_logs/app.log",
    formatter: str = "json",
    max_bytes: int = 1024 * 1024 * 10,
    backup_count: int = 5,
) -> dict:
    return {
        "level": level,
        "class": "logging.handlers.RotatingFileHandler",
        "formatter": formatter,
        "filename": filename,
        "maxBytes": max_bytes,
        "backupCount": backup_count,
    }


def get_api_handler(
    filename: str = "audit_logs/api.log",
    formatter: str = "api_json",
) -> dict:
    return {
        "level": API,
        "class": "django_activity_audit.handlers.AuditLogHandler",
        "filename": filename,
        "maxBytes": 1024 * 1024 * 10,  # 10MB
        "backupCount": 5,
        "formatter": formatter,
    }


def get_audit_handler(
    filename: str = "audit_logs/audit.log",
    formatter: str = "audit_json",
) -> dict:
    return {
        "level": AUDIT,
        "class": "django_activity_audit.handlers.AuditLogHandler",
        "filename": filename,
        "maxBytes": 1024 * 1024 * 10,  # 10MB
        "backupCount": 5,
        "formatter": formatter,
    }


def get_login_handler(
    filename: str = "audit_logs/login.log",
    formatter: str = "login_json",
) -> dict:
    return {
        "level": LOGIN,
        "class": "django_activity_audit.handlers.AuditLogHandler",
        "filename": filename,
        "maxBytes": 1024 * 1024 * 10,  # 10MB
        "backupCount": 5,
        "formatter": formatter,
    }


def push_usage_log(message: str, event: str, success: bool, error: str, extra: dict):
    """
    data:
        - message: message
        - user: user details
        - event: login or logout
        - success: true or false
        - error: error message
        - extra: {
            - cognito_id: cognito id
            - status_code: status code
        }
    """
    import logging
    from .signals import get_user_details

    logger = logging.getLogger("audit.login")

    data = {
        "user": get_user_details(),
        "event": event,
        "success": success,
        "error": error,
        "extra": extra,
    }

    logger.login(
        message,
        extra=data,
    )
