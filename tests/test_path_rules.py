"""Per-path rules for audit request logs (docs/specs/2026-11-03-path-rules.md).

Expected hashes are literals computed once with the standard library hmac
module, with AUDIT_HASH_SECRET = "test-hash-secret" from tests/test_settings.py.
"""

import asyncio

import pytest

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from rest_framework.test import APIClient

from activity_audit import middleware as audit_middleware
from activity_audit.middleware import AuditLoggingMiddleware
from activity_audit.shared_processors import (
    check_settings,
    mask_sensitive_values,
    path_rule,
)
from tests.test_audit import _emit_via_structlog
from tests.test_masking import BEARER, BEARER_HASH

VALID_RULES = [
    {
        "path": r"^/client_applications/login/?$",
        "mode": "hash",
        "request_target": ["access_key"],
        "request_headers": ["*"],
    },
    {
        "path": r"^/admin/client_applications/",
        "mode": "mask",
        "response_target": ["*"],
    },
    {"path": r"^/health/$", "mode": "skip"},
]

LOGIN_RULE = {
    "path": r"^/client_applications/login/?$",
    "mode": "hash",
    "request_target": ["access_key"],
    "response_target": ["session_id"],
    "request_headers": ["X-Client-Id"],
    "response_headers": ["X-Request-Id"],
}


def _line(request_repr, response_repr=None, request_type="internal", **fields):
    """An audit.request line as the middleware would bind it, rendered to JSON."""
    return _emit_via_structlog(
        "audit.request",
        "api",
        "Audit Internal Request",
        request_type=request_type,
        request_repr=request_repr,
        response_repr=response_repr or {},
        **fields,
    )


def _login_line(path="/client_applications/login/", request_type="internal"):
    return _line(
        {
            "method": "POST",
            "path": path,
            "query_params": {"access_key": "ak-q", "page": "1"},
            "headers": {"X-Client-Id": "client-42", "Accept": "application/json"},
            "body": {
                "access_key": "ak-live-7Q2",
                "app": {"access_key": "ak-nested"},
                "name": "Ada",
            },
        },
        {
            "headers": {"X-Request-Id": "req-9", "Content-Type": "application/json"},
            "body": {"session_id": "s-1", "access_key": "ak-out"},
        },
        request_type=request_type,
    )


@override_settings(
    AUDIT_PATH_RULES=[
        {"path": r"authors", "mode": "mask", "request_target": ["access_key"]},
        {"path": r"^/api/authors/$", "mode": "skip"},
    ]
)
def test_path_rule_returns_the_first_match_or_none():
    assert path_rule("/api/authors/")["mode"] == "mask"
    assert path_rule("/api/books/") is None


@override_settings(
    AUDIT_PATH_RULES=[
        {"path": r"^/api/authors/$", "mode": "skip"},
        {"path": r"^/x|/y$", "mode": "skip"},
    ]
)
def test_a_skip_rule_must_match_the_whole_path():
    assert path_rule("/api/authors/")["path"] == r"^/api/authors/$"
    # "$" would also match before a trailing newline if the rule used search.
    assert path_rule("/api/authors/\n") is None
    # "^/x|/y$" finds "/y" at the end of "/a/y", but it does not match the whole path.
    assert path_rule("/a/y") is None
    assert path_rule("/y")["path"] == r"^/x|/y$"


@pytest.mark.parametrize(
    "rules",
    [
        "not a list",
        [["^/a$", "mask"]],
        [{"path": "^/a$", "mode": "mask", "request_targets": ["access_key"]}],
        [{"mode": "mask", "request_target": ["access_key"]}],
        [{"path": "", "mode": "mask", "request_target": ["access_key"]}],
        [{"path": "(", "mode": "mask", "request_target": ["access_key"]}],
        [{"path": "^/a$", "mode": "drop", "request_target": ["access_key"]}],
        [{"path": "^/a$", "request_target": ["access_key"]}],
        [{"path": "^/a$", "mode": "mask", "request_target": "access_key"}],
        [{"path": "^/a$", "mode": "mask", "request_target": ["access_key", ""]}],
        [{"path": "^/a$", "mode": "mask", "request_headers": ["*", "Accept"]}],
        [{"path": "^/health/$", "mode": "skip", "request_headers": ["*"]}],
        [{"path": "health", "mode": "skip"}],
        [{"path": "^/health", "mode": "skip"}],
        [{"path": "/health/$", "mode": "skip"}],
        [{"path": "a{99999999999}", "mode": "mask", "request_target": ["access_key"]}],
        [{"path": "^/a$", "mode": "hash"}],
    ],
)
def test_check_settings_rejects_bad_path_rules(rules):
    with override_settings(AUDIT_PATH_RULES=rules), pytest.raises(ImproperlyConfigured):
        check_settings()


def test_check_settings_names_the_bad_rule():
    rules = [VALID_RULES[0], {"path": "health", "mode": "skip"}]
    with override_settings(AUDIT_PATH_RULES=rules):
        with pytest.raises(ImproperlyConfigured) as error:
            check_settings()

    assert "AUDIT_PATH_RULES[1]" in str(error.value)


@override_settings(AUDIT_PATH_RULES=VALID_RULES)
def test_check_settings_accepts_valid_path_rules():
    check_settings()


@pytest.mark.django_db
@override_settings(AUDIT_PATH_RULES=[{"path": r"^/api/authors/$", "mode": "skip"}])
def test_skip_rule_writes_no_request_line_and_the_view_still_runs(
    rendered_request_log,
):
    response = APIClient().get("/api/authors/")

    assert response.status_code == 200
    assert rendered_request_log == []


@override_settings(AUDIT_PATH_RULES=[{"path": r"^/api/authors/$", "mode": "skip"}])
def test_skip_rule_applies_on_the_async_path(request_log_capture):
    async def get_response(request):
        return HttpResponse("ok")

    middleware = AuditLoggingMiddleware(get_response)
    response = asyncio.run(middleware.__acall__(RequestFactory().get("/api/authors/")))

    assert response.status_code == 200
    assert request_log_capture.by_level("API") == []


@pytest.mark.django_db
@override_settings(
    AUDIT_PATH_RULES=[
        {"path": r"authors", "mode": "mask", "request_headers": ["Accept"]},
        {"path": r"^/api/authors/$", "mode": "skip"},
    ]
)
def test_an_earlier_hide_rule_wins_over_a_later_skip_rule(rendered_request_log):
    APIClient().get("/api/authors/")

    assert len(rendered_request_log) == 1


@pytest.mark.django_db
@override_settings(
    AUDIT_PATH_RULES=[
        {"path": r"^/api/authors/$", "mode": "mask", "request_headers": ["*"]}
    ]
)
def test_unregistered_urls_still_skip_a_path_that_has_a_rule(
    monkeypatch, rendered_request_log
):
    monkeypatch.setattr(audit_middleware, "UNREGISTERED_URLS", [r"^/api/authors/"])

    APIClient().get("/api/authors/")

    assert rendered_request_log == []


@override_settings(AUDIT_PATH_RULES=[LOGIN_RULE])
def test_hash_rule_hides_each_target_in_its_own_part_of_the_line():
    line = _login_line()
    request, response = line["request_repr"], line["response_repr"]

    assert request["query_params"] == {
        "access_key": "hmac-sha256:26916ade635a9e0c",
        "page": "1",
    }
    assert request["headers"] == {
        "X-Client-Id": "hmac-sha256:380e9e91029e9341",
        "Accept": "application/json",
    }
    assert request["body"] == {
        "access_key": "hmac-sha256:e7ec0a2193ca0425",
        "app": {"access_key": "hmac-sha256:bf81b877c2a0ccc2"},
        "name": "Ada",
    }
    assert response["headers"] == {
        "X-Request-Id": "hmac-sha256:67c97964c614e6c2",
        "Content-Type": "application/json",
    }
    # request_target does not reach the response side.
    assert response["body"] == {
        "session_id": "hmac-sha256:54bf4f5f88aeec2b",
        "access_key": "ak-out",
    }


@override_settings(AUDIT_PATH_RULES=[LOGIN_RULE])
def test_rules_do_not_touch_other_paths_or_external_lines():
    for line in (
        _login_line(path="/client_applications/logout/"),
        _login_line(request_type="external"),
    ):
        assert line["request_repr"]["body"]["access_key"] == "ak-live-7Q2"
        assert line["response_repr"]["body"]["session_id"] == "s-1"


@override_settings(
    AUDIT_PATH_RULES=[
        {"path": r"^/api/authors/$", "mode": "mask", "request_target": ["access_key"]}
    ]
)
def test_mask_rule_masks_its_targets_and_every_global_key_in_the_line():
    line = _line(
        {
            "path": "/api/authors/",
            "headers": {"Authorization": BEARER},
            "body": {"access_key": "ak-live-7Q2"},
        },
        extra={"password": "pw-7"},
    )

    assert line["request_repr"]["headers"] == {"Authorization": "[MASKED]"}
    assert line["request_repr"]["body"] == {"access_key": "[MASKED]"}
    assert line["extra"] == {"password": "[MASKED]"}


@override_settings(
    AUDIT_PATH_RULES=[
        {
            "path": r"^/api/authors/$",
            "mode": "mask",
            "request_target": ["*"],
            "response_target": ["*"],
        }
    ]
)
def test_star_body_targets_hide_whole_bodies_and_query_values():
    line = _line(
        {
            "method": "POST",
            "path": "/api/authors/",
            "query_params": {"page": "1", "q": "ada"},
            "headers": {"Accept": "application/json"},
            "body": {"name": "Ada"},
        },
        {"headers": {"Allow": "GET"}, "body": {"id": 1, "name": "Ada"}},
    )

    assert line["request_repr"] == {
        "method": "POST",
        "path": "/api/authors/",
        "query_params": {"page": "[MASKED]", "q": "[MASKED]"},
        "headers": {"Accept": "application/json"},
        "body": "[MASKED]",
    }
    assert line["response_repr"] == {"headers": {"Allow": "GET"}, "body": "[MASKED]"}


@override_settings(
    AUDIT_PATH_RULES=[
        {"path": r"^/api/authors/$", "mode": "hash", "request_headers": ["*"]}
    ]
)
def test_star_headers_hash_every_header_once():
    line = _line(
        {
            "path": "/api/authors/",
            "headers": {"Accept": "application/json", "Authorization": BEARER},
            "body": {"name": "Ada"},
        }
    )

    # Authorization is also a global key: it is hashed once, not twice.
    assert line["request_repr"]["headers"] == {
        "Accept": "hmac-sha256:8dc9f4428b931a88",
        "Authorization": BEARER_HASH,
    }
    assert line["request_repr"]["body"] == {"name": "Ada"}


@override_settings(
    AUDIT_PATH_RULES=[
        {"path": r"^/api/authors/$", "mode": "hash", "request_target": ["password"]}
    ]
)
def test_a_global_key_that_is_also_a_target_is_hashed_once():
    line = _line({"path": "/api/authors/", "body": {"password": "pw-7"}})

    assert line["request_repr"]["body"] == {"password": "hmac-sha256:3cadfc4158b0b214"}


@override_settings(
    AUDIT_PATH_RULES=[
        {
            "path": r"^/api/authors/$",
            "mode": "hash",
            "request_target": ["access_key"],
            "request_headers": ["x-client-id"],
        }
    ]
)
def test_target_and_header_names_match_any_case_and_separator():
    line = _line(
        {
            "path": "/api/authors/",
            "headers": {"X-CLIENT_ID": "client-42"},
            "body": {"AccessKey": "ak-case"},
        }
    )

    assert line["request_repr"]["headers"] == {
        "X-CLIENT_ID": "hmac-sha256:380e9e91029e9341"
    }
    assert line["request_repr"]["body"] == {"AccessKey": "hmac-sha256:22312dfa70aed266"}


@override_settings(
    AUDIT_PATH_RULES=[
        {"path": r"^/api/authors/$", "mode": "hash", "request_target": ["access_key"]}
    ],
    AUDIT_SENSITIVE_VALUE_FUNCTION="tests.test_masking.label_value",
)
def test_hash_rule_uses_the_project_value_function():
    line = _line({"path": "/api/authors/", "body": {"access_key": "ak-live-7Q2"}})

    assert line["request_repr"]["body"] == {"access_key": "[HIDDEN access_key len=11]"}


@override_settings(
    AUDIT_PATH_RULES=[
        {"path": r"authors", "mode": "mask", "request_target": ["access_key"]},
        {"path": r"^/api/authors/$", "mode": "hash", "request_target": ["access_key"]},
    ]
)
def test_only_the_first_matching_rule_applies():
    line = _line({"path": "/api/authors/", "body": {"access_key": "ak-live-7Q2"}})

    assert line["request_repr"]["body"] == {"access_key": "[MASKED]"}


@pytest.mark.django_db
@override_settings(
    AUDIT_PATH_RULES=[
        {
            "path": r"^/api/authors/$",
            "mode": "hash",
            "request_target": ["access_key"],
            "response_headers": ["Allow"],
        }
    ]
)
def test_hash_rule_through_the_middleware(rendered_request_log):
    response = APIClient().post(
        "/api/authors/",
        {"name": "Ada Lovelace", "experience": "Senior", "access_key": "ak-live-7Q2"},
        format="json",
    )

    assert response.status_code == 201
    line = rendered_request_log[0]
    assert line["request_repr"]["body"]["access_key"] == "hmac-sha256:e7ec0a2193ca0425"
    assert line["response_repr"]["headers"]["Allow"] == "hmac-sha256:39d70f71c0c66bd4"


@override_settings(
    AUDIT_PATH_RULES=[
        {"path": r"^/api/authors/$", "mode": "mask", "response_target": ["session_id"]}
    ]
)
def test_rules_apply_on_the_async_path(request_log_capture):
    async def get_response(request):
        return HttpResponse(
            '{"session_id": "s-1", "id": 7}', content_type="application/json"
        )

    middleware = AuditLoggingMiddleware(get_response)
    asyncio.run(middleware.__acall__(RequestFactory().get("/api/authors/")))

    record = request_log_capture.by_level("API")[0]
    assert record.response_repr["body"] == {"session_id": "[MASKED]", "id": 7}


@override_settings(
    AUDIT_SENSITIVE_KEYS_EXTRA=["body"],
    AUDIT_PATH_RULES=[
        {"path": r"^/api/authors/$", "mode": "hash", "request_target": ["access_key"]}
    ],
)
def test_a_part_named_like_a_global_key_is_hashed_once():
    line = _line({"path": "/api/authors/", "body": {"access_key": "ak-live-7Q2"}})

    # One hash of the raw body text "{'access_key': 'ak-live-7Q2'}".
    assert line["request_repr"]["body"] == "hmac-sha256:86c39a7f97330940"


@override_settings(
    AUDIT_PATH_RULES=[
        {"path": r"^/api/authors/$", "mode": "hash", "request_target": ["access_key"]}
    ]
)
def test_a_target_inside_a_global_key_value_is_hashed_once():
    line = _line({"path": "/api/authors/", "body": {"password": {"access_key": "A1"}}})

    # password is a global key: its raw value "{'access_key': 'A1'}" is hashed once.
    assert line["request_repr"]["body"] == {"password": "hmac-sha256:f75e00d57c2239f3"}


@override_settings(
    AUDIT_PATH_RULES=[
        {"path": r"^/api/authors/$", "mode": "hash", "request_target": ["access_key"]}
    ]
)
def test_rules_do_not_change_the_callers_line():
    request_repr = {"path": "/api/authors/", "body": {"access_key": "ak-live-7Q2"}}
    event = {
        "name": "audit.request",
        "request_type": "internal",
        "request_repr": request_repr,
    }

    mask_sensitive_values(None, "api", event)

    assert request_repr == {
        "path": "/api/authors/",
        "body": {"access_key": "ak-live-7Q2"},
    }


@override_settings(
    AUDIT_PATH_RULES=[
        {"path": r"^/api/authors/$", "mode": "hash", "request_target": ["access_key"]}
    ]
)
def test_rules_apply_only_to_audit_request_lines():
    event = {
        "name": "app.publications",
        "request_type": "internal",
        "request_repr": {
            "path": "/api/authors/",
            "body": {"access_key": "ak-live-7Q2"},
        },
    }

    line = mask_sensitive_values(None, "info", event)

    assert line["request_repr"]["body"] == {"access_key": "ak-live-7Q2"}


@override_settings(
    AUDIT_SENSITIVE_KEYS_EXTRA=["request_repr"],
    AUDIT_PATH_RULES=[
        {"path": r"^/api/authors/$", "mode": "hash", "request_target": ["access_key"]}
    ],
)
def test_a_side_named_like_a_global_key_is_hashed_once():
    line = _line({"path": "/api/authors/", "body": {"access_key": "ak-live-7Q2"}})

    # One hash of the raw text "{'path': '/api/authors/', 'body': {'access_key': 'ak-live-7Q2'}}".
    assert line["request_repr"] == "hmac-sha256:c2b4d0fc3c32fa78"
