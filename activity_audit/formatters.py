import datetime
import decimal
import json
import logging
import uuid


def _json_default(obj):
    """
    Serializer for non-JSON-native types.
    - datetime/date/time -> ISO 8601 string
    - Decimal -> float
    - UUID -> string
    - set -> list
    - bytes -> UTF-8 string (replace invalid)
    - Fallback -> str(obj)
    """
    if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
        return obj.isoformat()
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    # stringify the object
    return str(obj)


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
            # "extra": {},
        }

        # Add exception info if present for ERROR
        if record.exc_info:
            log_data["exception"] = "{}".format(self.formatException(record.exc_info))

        # Add extra fields if present
        # if hasattr(record, "extra"):
        #     log_data.update(record.extra)

        return json.dumps(log_data, default=_json_default)


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
            "user_id",
            "user_info",
            "request_repr",
            "response_repr",
            "error_message",
            "execution_time",
        ]

        for field in audit_fields:
            log_data[field] = getattr(record, field, "")
        return json.dumps(log_data, default=_json_default)


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
            "instance_repr",
            "user_id",
            "user_info",
            "extra",
        ]

        for field in audit_fields:
            value = getattr(record, field, "")
            # Parse JSON strings back to objects for proper serialization
            if field == "instance_repr" and isinstance(value, str):
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass  # Keep as string if parsing fails
            log_data[field] = value

        return json.dumps(log_data, default=_json_default)


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
            "user_id",
            "user_info",
            "event",
            "success",
            "error",
            "extra",
        ]

        for field in audit_fields:
            log_data[field] = getattr(record, field, "")

        return json.dumps(log_data, default=_json_default)
