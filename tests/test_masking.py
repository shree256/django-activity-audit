"""Sensitive values stay out of every audit log line (HWC-958, HWC-998).

Expected hashes are literals computed once with the standard library hmac
module (HMAC-SHA256 keyed with sha256("activity_audit.hash" + secret)), using
AUDIT_HASH_SECRET = "test-hash-secret" from tests/test_settings.py.
"""

import json

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
    hash_value,
    mask_sensitive_values,
    run_app_processors,
)
from tests.test_audit import _emit_via_structlog

BEARER = "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZGEifQ.c2lnbmF0dXJl"
BEARER_HASH = "hmac-sha256:ce79ca3145ff1c39"
NOT_CALLABLE = "not a function"


def add_app_fields(logger, method, event_dict):
    """An app processor. Tests name it in AUDIT_PROCESSORS."""
    event_dict["extra"] = {
        **event_dict.get("extra", {}),
        "seen_log_type": event_dict["log_type"],
        "secret_key": "sk_from_app_processor",
    }
    return event_dict


def label_value(key, value):
    """A project value function. Tests name it in AUDIT_SENSITIVE_VALUE_FUNCTION."""
    return f"[HIDDEN {key} len={len(value)}]"


class NotAProcessor:
    """A class path is importable and callable, but it is not a processor."""


@pytest.mark.django_db
def test_request_secrets_are_hashed_and_other_values_kept(rendered_request_log):
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
    assert headers["Authorization"] == BEARER_HASH
    assert headers["Cookie"] == "hmac-sha256:aec4c2c0c93f2a32"
    assert headers["X-Csrftoken"] == "hmac-sha256:c25904ff5fe44337"
    assert headers["Content-Type"] == "application/json"
    assert line["request_repr"]["body"] == {
        "name": "Ada Lovelace",
        "experience": "Senior",
        "secret_key": "hmac-sha256:716eb93a10a9a41f",
        "password": "hmac-sha256:2e9a665fc320b985",
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
        "Authorization": BEARER_HASH,
        "Accept": "application/json",
    }
    assert line["response_repr"]["body"] == {
        "accessToken": "hmac-sha256:488c6f7b329b9669",
        "refresh-token": "hmac-sha256:02510aa6e7b7c281",
        "results": [{"id": 7, "PASSWORD": "hmac-sha256:2ba28d6919b27a5b"}],
    }


def test_hash_is_keyed_and_falls_back_to_secret_key():
    assert hash_value("authorization", BEARER) == BEARER_HASH
    with override_settings(AUDIT_HASH_SECRET="other-hash-secret"):
        assert hash_value("authorization", BEARER) == "hmac-sha256:4f1cbfef236ec36b"
    for unset in (None, ""):
        with override_settings(AUDIT_HASH_SECRET=unset):
            # SECRET_KEY in tests/test_settings.py; "" must not become a public key.
            assert hash_value("authorization", BEARER) == "hmac-sha256:c8804f57eefa2a66"


def test_lone_surrogate_and_non_string_values_are_hashed():
    assert hash_value("password", "\ud800") == "hmac-sha256:d5ffd238bc58e24d"
    assert hash_value("pin", 1234) == "hmac-sha256:822889cfeda2c71c"


@pytest.mark.django_db
def test_lone_surrogate_in_a_secret_does_not_break_the_request(rendered_request_log):
    # Valid JSON text that json.loads turns into a lone surrogate.
    body = '{"name": "Sur Rogate", "experience": "x", "password": "\\ud800"}'

    response = APIClient().post(
        "/api/authors/", data=body, content_type="application/json"
    )

    assert response.status_code == 201
    assert len(rendered_request_log) == 1
    password = rendered_request_log[0]["request_repr"]["body"]["password"]
    assert password == "hmac-sha256:d5ffd238bc58e24d"


def test_none_and_empty_values_are_kept():
    masked = mask_sensitive_values(
        None, "info", {"extra": {"password": None, "access_token": ""}}
    )

    assert masked["extra"] == {"password": None, "access_token": ""}


def test_multi_value_dict_keeps_every_value_and_hashes_keys():
    query = QueryDict("tag=a&tag=b&password=pw-5&password=pw-6")

    masked = mask_sensitive_values(None, "info", {"extra": {"query": query}})

    # The whole raw value ['pw-5', 'pw-6'] is hashed as one string.
    assert masked["extra"]["query"] == {
        "tag": ["a", "b"],
        "password": "hmac-sha256:074e748efc41f74e",
    }


def test_model_row_password_is_hashed_without_changing_the_callers_dict():
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

    assert line["instance_repr"] == {
        "id": 3,
        "username": "ada",
        "password": "hmac-sha256:94b8fa28b75e0192",
    }
    assert row["password"] == "pbkdf2_sha256$870000$salt$hash"


def test_cycles_and_non_string_keys_do_not_break_masking():
    looped = {"password": "pw-1"}
    looped["self"] = looped

    masked = mask_sensitive_values(
        None, "info", {"extra": {"loop": looped, 404: "kept"}}
    )

    assert masked["extra"][404] == "kept"
    assert masked["extra"]["loop"]["password"] == "hmac-sha256:9330d2e2cf328258"
    assert "[TRUNCATED]" in json.dumps(masked)


def test_cycle_with_two_back_references_finishes():
    looped = {"password": "pw-3"}
    looped["x"] = looped
    looped["y"] = looped

    masked = mask_sensitive_values(None, "info", {"extra": looped})

    assert masked["extra"]["password"] == "hmac-sha256:aaf109b953e60854"
    assert masked["extra"]["x"] == "[TRUNCATED]"
    assert masked["extra"]["y"] == "[TRUNCATED]"


def test_shared_reference_that_is_not_a_cycle_is_hashed_in_both_places():
    shared = {"password": "pw-4", "id": 9}

    masked = mask_sensitive_values(None, "info", {"extra": {"a": shared, "b": shared}})

    expected = {"password": "hmac-sha256:786946e5909eb589", "id": 9}
    assert masked["extra"]["a"] == expected
    assert masked["extra"]["b"] == expected


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
@override_settings(AUDIT_SENSITIVE_KEYS_EXTRA=["token"])
def test_project_extra_keys_are_hashed(rendered_request_log):
    APIClient().get("/api/authors/?token=inv-5f2e&page=2")

    assert rendered_request_log[0]["request_repr"]["query_params"] == {
        "token": "hmac-sha256:7bf28ffa12f479a3",
        "page": "2",
    }


@override_settings(AUDIT_SENSITIVE_KEYS_DEFAULT=["x-api-key"])
def test_project_key_list_replaces_the_defaults():
    masked = mask_sensitive_values(
        None, "info", {"extra": {"Authorization": BEARER, "X-Api-Key": "k-123"}}
    )

    assert masked["extra"] == {
        "Authorization": BEARER,
        "X-Api-Key": "hmac-sha256:7b06e4339305e63b",
    }


@override_settings(AUDIT_SENSITIVE_KEYS_DEFAULT=[])
def test_empty_project_key_list_turns_hashing_off():
    masked = mask_sensitive_values(None, "info", {"extra": {"password": "pw-2"}})

    assert masked["extra"] == {"password": "pw-2"}


@override_settings(AUDIT_SENSITIVE_VALUE_FUNCTION="tests.test_masking.label_value")
def test_project_value_function_replaces_hashing():
    masked = mask_sensitive_values(
        None, "info", {"extra": {"accessToken": "at-77", "id": 7}}
    )

    assert masked["extra"] == {"accessToken": "[HIDDEN accessToken len=5]", "id": 7}


@override_settings(
    AUDIT_SENSITIVE_KEYS_EXTRA=["token"],
    AUDIT_SENSITIVE_VALUE_FUNCTION="tests.test_masking.label_value",
    AUDIT_PROCESSORS=["tests.test_masking.add_app_fields"],
)
def test_before_settings_are_configured_defaults_are_masked(monkeypatch):
    monkeypatch.setattr(type(settings), "configured", property(lambda self: False))
    event = {"log_type": "app", "extra": {"password": "pw-2", "token": "tk-3"}}

    assert run_app_processors(None, "info", event) == {
        "log_type": "app",
        "extra": {"password": "pw-2", "token": "tk-3"},
    }
    masked = mask_sensitive_values(None, "info", event)

    # No key to hash with and no project settings: default keys only, masked.
    assert masked["extra"] == {"password": "[MASKED]", "token": "tk-3"}


@pytest.mark.parametrize(
    "overrides, error",
    [
        ({"AUDIT_SENSITIVE_KEYS_DEFAULT": "password"}, ImproperlyConfigured),
        ({"AUDIT_SENSITIVE_KEYS_EXTRA": "token"}, ImproperlyConfigured),
        ({"AUDIT_SENSITIVE_KEYS_EXTRA": [b"token"]}, ImproperlyConfigured),
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
        (
            {"AUDIT_SENSITIVE_VALUE_FUNCTION": ["tests.test_masking.label_value"]},
            ImproperlyConfigured,
        ),
        ({"AUDIT_SENSITIVE_VALUE_FUNCTION": ""}, ImproperlyConfigured),
        (
            {"AUDIT_SENSITIVE_VALUE_FUNCTION": "tests.test_masking.NOT_CALLABLE"},
            ImproperlyConfigured,
        ),
        (
            {"AUDIT_SENSITIVE_VALUE_FUNCTION": "tests.test_masking.NotAProcessor"},
            ImproperlyConfigured,
        ),
        (
            {"AUDIT_SENSITIVE_VALUE_FUNCTION": "tests.test_masking.missing_function"},
            ImportError,
        ),
        ({"AUDIT_HASH_SECRET": ""}, ImproperlyConfigured),
        ({"AUDIT_HASH_SECRET": 1234}, ImproperlyConfigured),
        ({"AUDIT_HASH_SECRET": None, "SECRET_KEY": ""}, ImproperlyConfigured),
        (
            {
                "AUDIT_HASH_SECRET": None,
                "SECRET_KEY": "",
                "AUDIT_SENSITIVE_VALUE_FUNCTION": "tests.test_masking.label_value",
            },
            ImproperlyConfigured,
        ),
    ],
)
def test_check_settings_rejects_bad_values(overrides, error):
    with override_settings(**overrides), pytest.raises(error):
        check_settings()


@override_settings(
    AUDIT_SENSITIVE_KEYS_DEFAULT=("authorization",),
    AUDIT_SENSITIVE_KEYS_EXTRA=("token",),
    AUDIT_SENSITIVE_VALUE_FUNCTION="tests.test_masking.label_value",
    AUDIT_PROCESSORS=["tests.test_masking.add_app_fields"],
)
def test_check_settings_accepts_valid_values():
    check_settings()


def test_check_settings_never_shows_the_hash_secret():
    with override_settings(AUDIT_HASH_SECRET=b"raw-secret-bytes"):
        with pytest.raises(ImproperlyConfigured) as error:
            check_settings()

    assert "raw-secret-bytes" not in str(error.value)


@override_settings(AUDIT_PROCESSORS=["tests.test_masking.add_app_fields"])
def test_app_processor_runs_before_masking():
    line = _emit_via_structlog(
        "audit.request", "api", "Audit Internal Request", extra={"source": "test"}
    )

    assert line["extra"] == {
        "source": "test",
        "seen_log_type": "api",
        "secret_key": "hmac-sha256:75714f708db81e7c",
    }


def test_formatter_still_exposes_trim_log_fields_by_name():
    names = [getattr(p, "__name__", "") for p in get_stdlib_formatter()["processors"]]

    assert "trim_log_fields" in names
