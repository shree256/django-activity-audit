"""Sensitive values stay out of every audit log line (HWC-958, HWC-998)."""

import json
import logging

from types import MappingProxyType

import pytest

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import QueryDict
from django.test import override_settings
from rest_framework.test import APIClient

from activity_audit.config import get_stdlib_formatter
from activity_audit.shared_processors import (
    check_settings,
    mask_sensitive_values,
    run_app_processors,
)
from tests.conftest import LogCapture
from tests.test_audit import _emit_via_structlog

BEARER = "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZGEifQ.c2lnbmF0dXJl"
NOT_CALLABLE = "not a function"


def add_app_fields(logger, method, event_dict):
    """An app processor. Tests name it in AUDIT_PROCESSORS."""
    event_dict["extra"] = {
        **event_dict.get("extra", {}),
        "seen_log_type": event_dict["log_type"],
        "secret_key": "sk_from_app_processor",
    }
    return event_dict


class NotAProcessor:
    """A class path is importable and callable, but it is not a processor."""


@pytest.fixture
def rendered_request_log():
    """Each audit.request line as production renders it, parsed from JSON."""
    spec = get_stdlib_formatter()
    formatter_cls = spec.pop("()")
    capture = LogCapture()
    capture.setFormatter(formatter_cls(**spec))
    logger = logging.getLogger("audit.request")
    logger.addHandler(capture)
    yield capture.formatted_outputs
    logger.removeHandler(capture)


@pytest.mark.django_db
def test_request_secrets_are_masked_and_other_values_kept(rendered_request_log):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=BEARER, HTTP_X_CSRFTOKEN="csrf-9f8e7d")
    client.cookies["sessionid"] = "sess-4c1a9b"

    response = client.post(
        "/api/authors/",
        {
            "name": "Ada Lovelace",
            "experience": "Senior",
            "secret_key": "sk_live_51Hx",
            "password": "correct-horse",
        },
        format="json",
    )

    assert response.status_code == 201
    line = rendered_request_log[0]
    headers = line["request_repr"]["headers"]
    assert headers["Authorization"] == "[MASKED]"
    assert headers["Cookie"] == "[MASKED]"
    assert headers["X-Csrftoken"] == "[MASKED]"
    assert headers["Content-Type"] == "application/json"
    assert line["request_repr"]["body"] == {
        "name": "Ada Lovelace",
        "experience": "Senior",
        "secret_key": "[MASKED]",
        "password": "[MASKED]",
    }
    assert line["response_repr"]["body"]["name"] == "Ada Lovelace"
    rendered = json.dumps(rendered_request_log)
    for secret in (
        "eyJhbGci",
        "csrf-9f8e7d",
        "sess-4c1a9b",
        "sk_live_51Hx",
        "correct-horse",
    ):
        assert secret not in rendered


def test_keys_match_at_any_depth_case_and_separator():
    # Any Mapping that is not a dict, such as a requests CaseInsensitiveDict that an app logs.
    line = _emit_via_structlog(
        "audit.request",
        "api",
        "External Request",
        request_repr={
            "headers": MappingProxyType(
                {"Authorization": BEARER, "Accept": "application/json"}
            )
        },
        response_repr={
            "body": {
                "accessToken": "at-77",
                "refresh-token": "rt-88",
                "results": [{"id": 7, "PASSWORD": "pw-99"}],
            }
        },
    )

    assert line["request_repr"]["headers"] == {
        "Authorization": "[MASKED]",
        "Accept": "application/json",
    }
    assert line["response_repr"]["body"] == {
        "accessToken": "[MASKED]",
        "refresh-token": "[MASKED]",
        "results": [{"id": 7, "PASSWORD": "[MASKED]"}],
    }


def test_multi_value_dict_keeps_every_value_and_masks_keys():
    query = QueryDict("tag=a&tag=b&password=pw-5&password=pw-6")

    masked = mask_sensitive_values(None, "info", {"extra": {"query": query}})

    assert masked["extra"]["query"] == {"tag": ["a", "b"], "password": "[MASKED]"}


def test_model_row_password_is_masked_without_changing_the_callers_dict():
    row = {"id": 3, "username": "ada", "password": "pbkdf2_sha256$870000$salt$hash"}

    line = _emit_via_structlog(
        "audit.model",
        "audit",
        "UPDATE event by User (id: 3)",
        model="User",
        event_type="UPDATE",
        instance_id="3",
        instance_repr=row,
    )

    assert line["instance_repr"] == {"id": 3, "username": "ada", "password": "[MASKED]"}
    assert row["password"] == "pbkdf2_sha256$870000$salt$hash"


def test_cycles_and_non_string_keys_do_not_break_masking():
    looped = {"password": "pw-1"}
    looped["self"] = looped

    masked = mask_sensitive_values(
        None, "info", {"extra": {"loop": looped, 404: "kept"}}
    )

    assert masked["extra"][404] == "kept"
    assert masked["extra"]["loop"]["password"] == "[MASKED]"
    assert "[TRUNCATED]" in json.dumps(masked)


def test_cycle_with_two_back_references_finishes():
    looped = {"password": "pw-3"}
    looped["x"] = looped
    looped["y"] = looped

    masked = mask_sensitive_values(None, "info", {"extra": looped})

    assert masked["extra"]["password"] == "[MASKED]"
    assert masked["extra"]["x"] == "[TRUNCATED]"
    assert masked["extra"]["y"] == "[TRUNCATED]"


def test_shared_reference_that_is_not_a_cycle_is_masked_in_both_places():
    shared = {"password": "pw-4", "id": 9}

    masked = mask_sensitive_values(None, "info", {"extra": {"a": shared, "b": shared}})

    assert masked["extra"]["a"] == {"password": "[MASKED]", "id": 9}
    assert masked["extra"]["b"] == {"password": "[MASKED]", "id": 9}


@pytest.mark.django_db
def test_deeply_nested_body_is_truncated_and_the_line_is_still_written(
    rendered_request_log,
):
    body = json.loads('{"a":' * 300 + "1" + "}" * 300)
    body.update(name="Deep Nest", experience="Junior")

    response = APIClient().post("/api/authors/", body, format="json")

    assert response.status_code == 201
    assert len(rendered_request_log) == 1
    assert rendered_request_log[0]["request_repr"]["body"]["name"] == "Deep Nest"
    assert "[TRUNCATED]" in json.dumps(rendered_request_log[0])


@pytest.mark.django_db
@override_settings(AUDIT_MASK_KEYS_EXTRA=["token"])
def test_app_keys_from_settings_are_masked(rendered_request_log):
    APIClient().get("/api/authors/?token=inv-5f2e&page=2")

    assert rendered_request_log[0]["request_repr"]["query_params"] == {
        "token": "[MASKED]",
        "page": "2",
    }


@override_settings(
    AUDIT_MASK_KEYS_EXTRA=["token"],
    AUDIT_PROCESSORS=["tests.test_masking.add_app_fields"],
)
def test_before_settings_are_configured_only_defaults_apply(monkeypatch):
    monkeypatch.setattr(type(settings), "configured", property(lambda self: False))
    event = {"log_type": "app", "extra": {"password": "pw-2", "token": "tk-3"}}

    assert run_app_processors(None, "info", event) == {
        "log_type": "app",
        "extra": {"password": "pw-2", "token": "tk-3"},
    }
    masked = mask_sensitive_values(None, "info", event)

    assert masked["extra"] == {"password": "[MASKED]", "token": "tk-3"}


@pytest.mark.parametrize(
    "overrides, error",
    [
        ({"AUDIT_MASK_KEYS_EXTRA": "token"}, ImproperlyConfigured),
        ({"AUDIT_MASK_KEYS_EXTRA": [b"token"]}, ImproperlyConfigured),
        (
            {"AUDIT_PROCESSORS": "tests.test_masking.add_app_fields"},
            ImproperlyConfigured,
        ),
        (
            {"AUDIT_PROCESSORS": ["tests.test_masking.NOT_CALLABLE"]},
            ImproperlyConfigured,
        ),
        (
            {"AUDIT_PROCESSORS": ["tests.test_masking.NotAProcessor"]},
            ImproperlyConfigured,
        ),
        ({"AUDIT_PROCESSORS": ["tests.test_masking.missing_processor"]}, ImportError),
    ],
)
def test_check_settings_rejects_bad_values(overrides, error):
    with override_settings(**overrides), pytest.raises(error):
        check_settings()


@override_settings(
    AUDIT_MASK_KEYS_EXTRA=("token",),
    AUDIT_PROCESSORS=["tests.test_masking.add_app_fields"],
)
def test_check_settings_accepts_valid_values():
    check_settings()


@override_settings(AUDIT_PROCESSORS=["tests.test_masking.add_app_fields"])
def test_app_processor_runs_before_masking():
    line = _emit_via_structlog(
        "audit.request", "api", "Audit Internal Request", extra={"source": "test"}
    )

    assert line["extra"] == {
        "source": "test",
        "seen_log_type": "api",
        "secret_key": "[MASKED]",
    }


def test_formatter_still_exposes_trim_log_fields_by_name():
    names = [getattr(p, "__name__", "") for p in get_stdlib_formatter()["processors"]]

    assert "trim_log_fields" in names
