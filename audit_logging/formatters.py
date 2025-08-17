import logging
import datetime
import json


class JsonFormatter(logging.Formatter):
    def __init__(self, timestamp_format: str = "%Y-%m-%d %H:%M:%S.%f"):
        super().__init__()
        self.timestamp_format = timestamp_format

    def format(
        self,
        record,
    ):
        log_data = {
            "timestamp": datetime.datetime.fromtimestamp(record.created).strftime(
                self.timestamp_format
            )[:-3],
            "level": record.levelname,
            "name": record.name,
            "path": record.pathname,
            "module": record.module,
            "function": record.funcName,
            "message": record.getMessage(),
            "exception": "",
            "request": "",
            "extra": "",
        }

        # Add exception info if present for ERROR
        if record.exc_info:
            log_data["exception"] = "{}".format(self.formatException(record.exc_info))

        # Add request info if available
        if hasattr(record, "request"):
            log_data["request"] = {
                "method": getattr(record.request, "method", None),
                "path": getattr(record.request, "path", None),
                "user": str(getattr(record.request, "user", None)),
            }

        # Add extra fields if present
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        return json.dumps(log_data)


class APIFormatter(logging.Formatter):
    """Custom formatter for audit logs that ensures consistent JSON formatting."""

    def __init__(self, timestamp_format: str = "%Y-%m-%d %H:%M:%S.%f"):
        super().__init__()
        self.timestamp_format = timestamp_format

    def format(self, record):
        # Start with basic log data
        log_data = {
            "timestamp": datetime.datetime.fromtimestamp(record.created).strftime(
                self.timestamp_format
            )[:-3],
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }

        # Add all audit-specific fields if they exist
        audit_fields = [
            "service_name",
            "request_type",
            "protocol",
            "request_repr",
            "response_repr",
            "error_message",
            "execution_time",
        ]

        for field in audit_fields:
            log_data[field] = getattr(record, field)

        return json.dumps(log_data)


class AuditFormatter(logging.Formatter):
    def __init__(self, timestamp_format: str = "%Y-%m-%d %H:%M:%S.%f"):
        super().__init__()
        self.timestamp_format = timestamp_format

    def format(self, record):
        log_data = {
            "timestamp": datetime.datetime.fromtimestamp(record.created).strftime(
                self.timestamp_format
            )[:-3],
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }

        audit_fields = [
            "model",
            "event_type",
            "instance_id",
            "user",
            "extra",
        ]

        for field in audit_fields:
            log_data[field] = getattr(record, field)

        return json.dumps(log_data)


class LoginFormatter(logging.Formatter):
    def __init__(self, timestamp_format: str = "%Y-%m-%d %H:%M:%S.%f"):
        super().__init__()
        self.timestamp_format = timestamp_format

    def format(self, record):
        log_data = {
            "timestamp": datetime.datetime.fromtimestamp(record.created).strftime(
                self.timestamp_format
            )[:-3],
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }

        audit_fields = [
            "user",
            "event",
            "success",
            "error",
            "extra",
        ]

        for field in audit_fields:
            log_data[field] = getattr(record, field)

        return json.dumps(log_data)
