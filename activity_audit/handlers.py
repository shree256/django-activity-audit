import logging

from logging.handlers import RotatingFileHandler

from .formatters import APIFormatter, AuditFormatter, LoginFormatter


class BaseAuditHandler(RotatingFileHandler):
    """Base handler for all audit logs with common emit logic."""

    def emit(self, record):
        """
        Emit a record with additional values for audit-specific fields.
        """
        try:
            # Handle extra if present
            if hasattr(record, "extra"):
                for key, value in record.extra.items():
                    setattr(record, key, value)

            super().emit(record)

        except Exception as e:
            self.handleError(record)
            # Log the error to the root logger
            logging.getLogger().error(f"Error in AuditLogHandler: {str(e)}")


class APILogHandler(BaseAuditHandler):
    """Handler for API audit logs with default APIFormatter."""

    def __init__(
        self,
        filename,
        mode="a",
        maxBytes=0,
        backupCount=0,
        encoding=None,
        delay=False,
    ):
        super().__init__(filename, mode, maxBytes, backupCount, encoding, delay)
        self.setFormatter(APIFormatter())


class AuditLogHandler(BaseAuditHandler):
    """Handler for model audit logs with default AuditFormatter."""

    def __init__(
        self,
        filename,
        mode="a",
        maxBytes=0,
        backupCount=0,
        encoding=None,
        delay=False,
    ):
        super().__init__(filename, mode, maxBytes, backupCount, encoding, delay)
        self.setFormatter(AuditFormatter())


class LoginLogHandler(BaseAuditHandler):
    """Handler for login audit logs with default LoginFormatter."""

    def __init__(
        self,
        filename,
        mode="a",
        maxBytes=0,
        backupCount=0,
        encoding=None,
        delay=False,
    ):
        super().__init__(filename, mode, maxBytes, backupCount, encoding, delay)
        self.setFormatter(LoginFormatter())
