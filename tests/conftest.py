import json
import logging
import os

from types import SimpleNamespace

import django
import pytest


def pytest_configure():
    """Configure Django settings for pytest."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.test_settings")
    django.setup()


class LogCapture(logging.Handler):
    """In-memory log handler that captures records during a test.

    When a formatter is attached (via setFormatter), each record is also
    formatted immediately on emit and stored in `formatted_outputs` as a parsed
    dict. This matters for formatters that read contextvars state at format
    time — by the time assertions run, that state may be gone.
    """

    def __init__(self):
        super().__init__(level=1)
        self.records = []
        self.formatted_outputs = []

    def emit(self, record):
        self.records.append(record)
        if self.formatter:
            try:
                self.formatted_outputs.append(json.loads(self.formatter.format(record)))
            except Exception:
                pass

    def clear(self):
        self.records.clear()
        self.formatted_outputs.clear()

    def by_event_type(self, event_type):
        """Return SimpleNamespace objects parsed from structlog records.

        structlog's wrap_for_formatter stores the processed event dict directly
        as record.msg (a Python dict). If that's available, use it directly.
        Otherwise fall back to JSON-parsing getMessage() for stdlib-formatted
        records, then to a plain attribute lookup.
        """
        result = []
        for r in self.records:
            if isinstance(r.msg, dict):
                if r.msg.get("event_type") == event_type:
                    result.append(SimpleNamespace(**r.msg))
                continue
            try:
                data = json.loads(r.getMessage())
                if data.get("event_type") == event_type:
                    result.append(SimpleNamespace(**data))
            except (json.JSONDecodeError, AttributeError):
                if getattr(r, "event_type", None) == event_type:
                    result.append(r)
        return result

    def by_level(self, level_name):
        result = []
        for r in self.records:
            if r.levelname != level_name:
                continue
            if isinstance(r.msg, dict):
                result.append(SimpleNamespace(**r.msg))
                continue
            try:
                data = json.loads(r.getMessage())
                result.append(SimpleNamespace(**data))
            except (json.JSONDecodeError, AttributeError):
                result.append(r)
        return result


@pytest.fixture
def model_log_capture():
    """Attach a capture handler to the model audit logger for the duration of a test."""
    capture = LogCapture()
    logger = logging.getLogger("audit.model")
    logger.addHandler(capture)
    yield capture
    logger.removeHandler(capture)


@pytest.fixture
def request_log_capture():
    """Attach a capture handler to the request audit logger for the duration of a test."""
    capture = LogCapture()
    logger = logging.getLogger("audit.request")
    logger.addHandler(capture)
    yield capture
    logger.removeHandler(capture)


@pytest.fixture
def rendered_request_log():
    """Each audit.request line as production renders it, parsed from JSON."""
    from activity_audit.config import get_stdlib_formatter

    spec = get_stdlib_formatter()
    formatter_cls = spec.pop("()")
    capture = LogCapture()
    capture.setFormatter(formatter_cls(**spec))
    logger = logging.getLogger("audit.request")
    logger.addHandler(capture)
    yield capture.formatted_outputs
    logger.removeHandler(capture)


@pytest.fixture
def app_log_capture():
    """Attach a capturing handler with the structlog JSON formatter to the
    app.publications logger.

    Records are formatted immediately on emit so that request_id is read from
    contextvars while the request is still active.
    """
    from activity_audit.config import get_stdlib_formatter

    formatter_kwargs = get_stdlib_formatter()
    formatter_cls = formatter_kwargs.pop("()")

    capture = LogCapture()
    capture.setFormatter(formatter_cls(**formatter_kwargs))

    logger = logging.getLogger("app.publications")
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(capture)
    yield capture
    logger.removeHandler(capture)
    logger.setLevel(previous_level)


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def author_data():
    return {
        "name": "Test Author",
        "experience": "Experienced writer with 10 years in publishing",
    }
