import datetime
import decimal
import sys

from collections.abc import Mapping
from functools import lru_cache

import orjson
import structlog

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.crypto import salted_hmac
from django.utils.module_loading import import_string
from structlog.processors import CallsiteParameter

from activity_audit.constants import LogType


def _orjson_dumps(*args, **kwargs):
    return orjson.dumps(*args, **kwargs).decode()


def _json_default(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    return str(obj)


def _audit_timestamp(logger, method, event_dict):
    """Timestamp in the same format as the existing formatters: 'YYYY-MM-DD HH:MM:SS.mmm'."""
    event_dict["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[
        :-3
    ]
    return event_dict


def _uppercase_level(logger, method, event_dict):
    """Uppercase level name to match AUDIT / API / LOGIN convention."""
    if "level" in event_dict:
        event_dict["level"] = event_dict["level"].upper()
    return event_dict


def _rename_structlog_keys(logger, method, event_dict):
    """
    Rename structlog default keys to match the existing JSON field names:
      event  → message
      logger → name
    """
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    if "logger" in event_dict:
        event_dict["name"] = event_dict.pop("logger")
    return event_dict


def _detect_process_log_type() -> str:
    argv = " ".join(sys.argv)
    if "beat" in argv:
        return LogType.CELERYBEAT
    if "celery" in argv:
        return LogType.CELERYWORKER
    return LogType.AUDIT


_PROCESS_LOG_TYPE = _detect_process_log_type()

_LOG_TYPE_MAP = {
    "audit.model": _PROCESS_LOG_TYPE,
    "audit.request": LogType.API,
    "audit.login": LogType.LOGIN,
}


def _add_log_type(logger, method, event_dict):
    """Add log_type based on logger name; all celery.* loggers get the process type."""
    name = event_dict.get("name", "")
    if name in _LOG_TYPE_MAP:
        event_dict["log_type"] = _LOG_TYPE_MAP[name]
    elif name.startswith("celery"):
        event_dict["log_type"] = _PROCESS_LOG_TYPE
    else:
        event_dict["log_type"] = LogType.APP
    return event_dict


_APP_FIELDS = frozenset(
    {
        "timestamp",
        "level",
        "name",
        "message",
        "log_type",
        "filename",
        "func_name",
        "request_id",
        "exception",
        "extra",
    }
)

_AUDIT_FIELDS = frozenset(
    {
        "timestamp",
        "level",
        "name",
        "message",
        "log_type",
        "model",
        "event_type",
        "request_id",
        "instance_id",
        "instance_repr",
        "user_id",
        "user_info",
        "extra",
    }
)

_API_FIELDS = frozenset(
    {
        "timestamp",
        "level",
        "name",
        "message",
        "log_type",
        "service_name",
        "request_type",
        "protocol",
        "request_id",
        "user_id",
        "user_info",
        "request_repr",
        "response_repr",
        "error_message",
        "execution_time",
        "extra",
    }
)

_FIELDS_BY_LOG_TYPE = {
    LogType.APP: _APP_FIELDS,
    LogType.CELERYBEAT: _APP_FIELDS,
    LogType.CELERYWORKER: _APP_FIELDS,
    LogType.AUDIT: _AUDIT_FIELDS,
    LogType.API: _API_FIELDS,
}


def trim_log_fields(logger, method, event_dict):
    """Keep only the required fields for each log type."""
    allowed = _FIELDS_BY_LOG_TYPE.get(event_dict.get("log_type"))
    if allowed is not None:
        return {k: v for k, v in event_dict.items() if k in allowed}
    return event_dict


_STANDARD_KEYS = frozenset(
    {
        "timestamp",
        "level",
        "name",
        "message",
        "log_type",
        "filename",
        "func_name",
        "stack_info",
        "exception",
        "request_id",
        "_record",
        "_from_structlog",
        # audit.model fields
        "model",
        "event_type",
        "instance_id",
        "instance_repr",
        "user_id",
        "user_info",
        "extra",
        # audit.request fields
        "service_name",
        "request_type",
        "protocol",
        "request_repr",
        "response_repr",
        "error_message",
        "execution_time",
        # audit.login fields
        "event",
        "success",
        "error",
    }
)


def _collect_extra(logger, method, event_dict):
    """Move all caller-supplied kwargs that aren't standard fields into 'extra'."""
    extra = {k: event_dict.pop(k) for k in list(event_dict) if k not in _STANDARD_KEYS}
    if extra:
        event_dict["extra"] = extra
    return event_dict


MASKED = "[MASKED]"
TRUNCATED = "[TRUNCATED]"
# orjson drops the whole line past 254 nested levels, so stop well before that.
MAX_MASK_DEPTH = 64
HASH_SALT = "activity_audit.hash"

# HWC-958. AUDIT_SENSITIVE_KEYS_DEFAULT replaces these.
# Compared after _normalize_key, so case, "-" and "_" do not matter.
DEFAULT_SENSITIVE_KEYS = (
    "authorization",
    "cookie",
    "set-cookie",
    "x-csrftoken",
    "secret_key",
    "access_token",
    "refresh_token",
    "password",
)


def _normalize_key(key):
    return key.lower().replace("-", "").replace("_", "")


def _setting(name, default=()):
    # Apps build formatters while their settings module loads, so read per call.
    return getattr(settings, name, default) if settings.configured else default


@lru_cache(maxsize=None)
def _sensitive_keys(default, extra):
    return frozenset(_normalize_key(key) for key in default + extra)


@lru_cache(maxsize=None)
def _load_processors(paths):
    return tuple(import_string(path) for path in paths)


def run_app_processors(logger, method, event_dict):
    """Run the processors that AUDIT_PROCESSORS names, in order."""
    for processor in _load_processors(tuple(_setting("AUDIT_PROCESSORS"))):
        event_dict = processor(logger, method, event_dict)
    return event_dict


def hash_value(key, value):
    """The default AUDIT_SENSITIVE_VALUE_FUNCTION: a keyed hash of the value.

    None and "" stay as they are, so a missing value does not look like a secret.
    """
    if value is None or value == "":
        return value
    # None makes salted_hmac use SECRET_KEY. An empty secret would hash with a public key.
    secret = _setting("AUDIT_HASH_SECRET", None) or None
    # A JSON body can carry a lone surrogate, which strict UTF-8 cannot encode.
    data = str(value).encode("utf-8", "surrogatepass")
    digest = salted_hmac(HASH_SALT, data, secret=secret, algorithm="sha256")
    return "hmac-sha256:" + digest.hexdigest()[:16]


def _masked(key, value):
    return MASKED


def _value_function():
    if not settings.configured:
        # No key to hash with, and no project function to load.
        return _masked
    path = _setting("AUDIT_SENSITIVE_VALUE_FUNCTION", None)
    return _load_processors((path,))[0] if path else hash_value


def _mask(value, keys, hide, depth, path):
    if depth > MAX_MASK_DEPTH:
        return TRUNCATED
    if not isinstance(value, (Mapping, list, tuple)):
        return value
    # path holds ids of containers above this one. The depth cap alone is too
    # slow for a cycle with two back-references: the work doubles per level.
    if id(value) in path:
        return TRUNCATED
    path.add(id(value))
    try:
        if isinstance(value, Mapping):
            # dict.items() reads raw storage: MultiValueDict.items() keeps only the last value.
            items = dict.items(value) if isinstance(value, dict) else value.items()
            return {
                key: hide(key, item)
                if isinstance(key, str) and _normalize_key(key) in keys
                else _mask(item, keys, hide, depth + 1, path)
                for key, item in items
            }
        return [_mask(item, keys, hide, depth + 1, path) for item in value]
    finally:
        path.discard(id(value))


def mask_sensitive_values(logger, method, event_dict):
    """Return a copy with each sensitive key's value, at any depth, replaced."""
    keys = _sensitive_keys(
        tuple(_setting("AUDIT_SENSITIVE_KEYS_DEFAULT", DEFAULT_SENSITIVE_KEYS)),
        tuple(_setting("AUDIT_SENSITIVE_KEYS_EXTRA")),
    )
    return _mask(event_dict, keys, _value_function(), 0, set())


def check_settings():
    """Raise at startup, not on the first log line, when a setting is wrong."""
    for name in (
        "AUDIT_SENSITIVE_KEYS_DEFAULT",
        "AUDIT_SENSITIVE_KEYS_EXTRA",
        "AUDIT_PROCESSORS",
    ):
        value = _setting(name)
        if not isinstance(value, (list, tuple)) or not all(
            isinstance(item, str) for item in value
        ):
            raise ImproperlyConfigured(
                f"{name} must be a list or tuple of strings, got {value!r}."
            )
    function = _setting("AUDIT_SENSITIVE_VALUE_FUNCTION", None)
    if function is not None and (not isinstance(function, str) or not function):
        raise ImproperlyConfigured(
            f"AUDIT_SENSITIVE_VALUE_FUNCTION must be a dotted path, got {function!r}."
        )
    secret = _setting("AUDIT_HASH_SECRET", None)
    if secret is not None and (not isinstance(secret, str) or not secret):
        # Never show the value: it is the hash key.
        raise ImproperlyConfigured("AUDIT_HASH_SECRET must be a non-empty string.")
    if secret is None:
        # A project function can still call hash_value, which then needs SECRET_KEY.
        settings.SECRET_KEY  # Django raises ImproperlyConfigured when it is empty.
    for name, paths in (
        ("AUDIT_PROCESSORS", tuple(_setting("AUDIT_PROCESSORS"))),
        ("AUDIT_SENSITIVE_VALUE_FUNCTION", (function,) if function else ()),
    ):
        for path, loaded in zip(paths, _load_processors(paths)):
            if isinstance(loaded, type) or not callable(loaded):
                raise ImproperlyConfigured(f"{name} entry {path!r} is not callable.")


shared_processors = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.PositionalArgumentsFormatter(),
    _audit_timestamp,
    _uppercase_level,
    _rename_structlog_keys,
    _add_log_type,
    structlog.processors.CallsiteParameterAdder(
        [
            CallsiteParameter.FILENAME,
            CallsiteParameter.FUNC_NAME,
        ]
    ),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.ExceptionRenderer(),
    _collect_extra,
    run_app_processors,
    mask_sensitive_values,
]
