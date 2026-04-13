import logging
import queue

from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler

from .formatters import APIFormatter, AuditFormatter, JsonFormatter, LoginFormatter


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


# ASYNC ------------------------------------------------------
class AsyncBaseAuditHandler(QueueHandler):
    """
    Base async handler. Enqueues records on the calling thread; a background
    QueueListener thread does the actual file write via the wrapped sync handler.

    Subclasses pass the concrete sync handler class and formatter via
    _sync_handler_class and _formatter_class.
    """

    _sync_handler_class = None
    _formatter_class = None

    def __init__(
        self,
        filename,
        mode="a",
        maxBytes=0,
        backupCount=0,
        encoding=None,
        delay=False,
    ):
        log_queue = queue.Queue(-1)
        super().__init__(log_queue)

        sync_handler = self._sync_handler_class(
            filename, mode, maxBytes, backupCount, encoding, delay
        )
        self._listener = QueueListener(
            log_queue, sync_handler, respect_handler_level=True
        )
        self._listener.start()

    def close(self):
        self._listener.stop()
        super().close()


class AsyncAPILogHandler(AsyncBaseAuditHandler):
    """Non-blocking handler for API audit logs."""

    _sync_handler_class = APILogHandler
    _formatter_class = APIFormatter


class AsyncAuditLogHandler(AsyncBaseAuditHandler):
    """Non-blocking handler for model audit logs."""

    _sync_handler_class = AuditLogHandler
    _formatter_class = AuditFormatter


class AsyncLoginLogHandler(AsyncBaseAuditHandler):
    """Non-blocking handler for login audit logs."""

    _sync_handler_class = LoginLogHandler
    _formatter_class = LoginFormatter


class AsyncJsonHandler(QueueHandler):
    """
    Non-blocking handler for general JSON logs. Wraps a RotatingFileHandler
    with JsonFormatter on the background thread.
    """

    def __init__(
        self,
        filename,
        mode="a",
        maxBytes=0,
        backupCount=0,
        encoding=None,
        delay=False,
    ):
        log_queue = queue.Queue(-1)
        super().__init__(log_queue)

        sync_handler = RotatingFileHandler(
            filename, mode, maxBytes, backupCount, encoding, delay
        )
        sync_handler.setFormatter(JsonFormatter())
        self._listener = QueueListener(
            log_queue, sync_handler, respect_handler_level=True
        )
        self._listener.start()

    def close(self):
        self._listener.stop()
        super().close()
