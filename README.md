# Django Activity Audit

A Django package that extends the default logging mechanism to track CRUD operations and container logs.

## Features

- Automatic logging of CRUD operations (Create, Read, Update, Delete)
- Tracks both HTTP requests and model changes
- Custom log levels Audit(21) and API(22) for CRUD and Request-Response auditing.
- Structured JSON logs for audit trails
- Human-readable container logs
- Console-only output via structlog, ready for pipeline ingestion (Vector, CloudWatch, etc.)

## Installation

1. Install the package:
```bash
pip install django-activity-audit
```

This also installs [`structlog`](https://www.structlog.org/) and [`orjson`](https://github.com/ijl/orjson) as required dependencies.

2. Add 'activity_audit' to your INSTALLED_APPS in settings.py:
```python
INSTALLED_APPS = [
    ...
    'activity_audit',
]
```

3. Add the middleware to your MIDDLEWARE in settings.py:
```python
MIDDLEWARE = [
    ...
    'activity_audit.middleware.AuditLoggingMiddleware',
]
```

4. Configure logging in settings.py:

Import the formatter helpers from `activity_audit.config`:

```python
from activity_audit.config import get_plain_formatter, get_stdlib_formatter
```

- `get_stdlib_formatter()` — structlog JSON renderer. Use in staging/production where logs are ingested by a pipeline (Vector, CloudWatch, etc.).
- `get_plain_formatter()` — structlog plain-text renderer. Use locally for human-readable console output.

**Local development** (plain text output):

```python
from activity_audit.config import get_plain_formatter, get_stdlib_formatter

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structlog": get_stdlib_formatter(),
        "default":   get_plain_formatter(),
    },
    "handlers": {
        "console":        {"class": "logging.StreamHandler", "formatter": "default"},
        "console_struct": {"class": "logging.StreamHandler", "formatter": "structlog"},
    },
    "root": {
        "level": "INFO",
        "handlers": ["console"],   # plain text fallback for all loggers
    },
    "loggers": {
        # Structlog owns these — explicit handler, no propagation to avoid double output
        "audit.model":   {"handlers": ["console_struct"], "propagate": False},
        "audit.request": {"handlers": ["console_struct"], "propagate": False},
        "audit.login":   {"handlers": ["console_struct"], "propagate": False},

        # Celery — structlog formats log_type correctly
        "celery":        {"level": "INFO", "handlers": ["console_struct"], "propagate": False},
        "celery.task":   {"level": "INFO", "handlers": ["console_struct"], "propagate": False},
        "celery.beat":   {"level": "INFO", "handlers": ["console_struct"], "propagate": False},

        # Third-party noise control — WARNING only, routed to root
        "django.db.backends": {"level": "WARNING", "handlers": [], "propagate": True},
        "boto3":              {"level": "WARNING", "handlers": [], "propagate": True},
        "botocore":           {"level": "WARNING", "handlers": [], "propagate": True},

        # Framework loggers
        "django":        {"level": "INFO", "handlers": [], "propagate": True},
        "uvicorn":       {"level": "INFO", "handlers": [], "propagate": True},
        "uvicorn.error": {"level": "INFO", "handlers": [], "propagate": True},
        "uvicorn.access":{"level": "INFO", "handlers": [], "propagate": True},
    },
}
```

**Staging / production** (structured JSON output): identical structure, but the `root` handler also uses `console_struct` (or keep `console` for mixed output — both handlers use the same `StreamHandler` class):

```python
"root": {
    "level": "INFO",
    "handlers": ["console"],
}
```

---

### When to add a logger entry

Add an explicit logger entry when you need **any** of the following:

| Situation | What to set |
|-----------|-------------|
| Route to structured JSON (`console_struct`) | `handlers: ["console_struct"], propagate: False` |
| Suppress a noisy third-party library | `level: "WARNING", handlers: [], propagate: True` |
| Prevent double output for a structlog-owned logger | `handlers: ["console_struct"], propagate: False` |
| Change the log level for a specific namespace | Set `level` explicitly |

**Do not** add a logger entry if the default behaviour is acceptable — a logger with no entry propagates to `root` and is emitted in plain text at INFO level. That is the correct behaviour for most application loggers.

### Silencing audit loggers (route to root instead of structlog)

By default `audit.model`, `audit.request`, and `audit.login` are pointed at `console_struct` with `propagate: False` so only the structlog-formatted JSON line is emitted.

To stop structlog from handling them and fall back to the plain-text root logger instead, set `handlers: []` and `propagate: True`:

```python
"loggers": {
    "audit.model":   {"handlers": [], "propagate": True},
    "audit.request": {"handlers": [], "propagate": True},
    "audit.login":   {"handlers": [], "propagate": True},
}
```

This routes all three through the `root` logger (`console` handler, `default` / plain-text formatter). Use this when you want to completely disable structured audit output — for example, in a minimal local environment or during debugging.

5. Configure the service name in `settings.py` (optional, defaults to `"default"`):
```python
AUDIT_SERVICE_NAME = "my_service"
```

6. For external services logging, extend ```HTTPClient or SFTPClient```
```python
class ExternalService(HTTPClient):
    def __init__(self):
        super().__init__("service_name")

    def connect(self):
        url = "https://www.sample.com"
        response = self.get(url) # sample log structure below
```

8. Create ```audit_logs``` folder in project directory

## Settings

All settings are optional.

| Setting | Default | What it does |
|---|---|---|
| `AUDIT_SENSITIVE_KEYS_DEFAULT` | the 8 keys below | Keys whose values are hidden. If you set it, it replaces the defaults. An empty list, with an empty `AUDIT_SENSITIVE_KEYS_EXTRA`, turns hiding off. |
| `AUDIT_SENSITIVE_KEYS_EXTRA` | `[]` | More keys to hide, added to the list above. |
| `AUDIT_SENSITIVE_VALUE_FUNCTION` | the built-in hash | Dotted path to your own function that replaces a sensitive value. |
| `AUDIT_HASH_SECRET` | `SECRET_KEY` | The key for the built-in hash. |
| `AUDIT_PROCESSORS` | `[]` | Dotted paths to your own structlog processors. They run on every log line, in order. |
| `AUDIT_PATH_RULES` | `[]` | Rules that hash, mask or skip the request log line of chosen paths. See "Per-path rules". |
| `AUDIT_UNREGISTERED_URLS_DEFAULT` | `[r"^/admin/", r"^/static/", r"^/favicon.ico$"]` | URL patterns that are not logged. If you set it, it replaces the defaults. |
| `AUDIT_UNREGISTERED_URLS_EXTRA` | `[]` | More URL patterns that are not logged, added to the list above. |
| `AUDIT_REGISTERED_URLS` | `[]` | If you set it, only the URLs that match are logged. A URL that also matches an unregistered pattern is still not logged. |
| `AUDIT_SERVICE_NAME` | `"default"` | The `service_name` value in the middleware's request logs. `HTTPClient` takes its name from its constructor. |

The app checks `AUDIT_SENSITIVE_KEYS_DEFAULT`, `AUDIT_SENSITIVE_KEYS_EXTRA`, `AUDIT_SENSITIVE_VALUE_FUNCTION`, `AUDIT_HASH_SECRET`, `AUDIT_PROCESSORS` and `AUDIT_PATH_RULES` at startup. Each of these stops the start with an error:

- A key list or `AUDIT_PROCESSORS` value that is not a list or tuple of strings.
- An `AUDIT_SENSITIVE_VALUE_FUNCTION` or `AUDIT_HASH_SECRET` that is not a non-empty string.
- A path that does not import.
- A path to a class, or to something else that is not callable.
- An empty `SECRET_KEY` when `AUDIT_HASH_SECRET` is not set.
- A path rule that breaks a rule in "Per-path rules" below. The error gives the rule's position, such as `AUDIT_PATH_RULES[1]`.

### Sensitive values

The package hides sensitive values in every log line before it writes the line. This includes request logs, model change logs, login logs and app logs. When a key matches, at any depth, the package replaces its value with a keyed hash, such as `"hmac-sha256:ce79ca3145ff1c39"`.

The default keys are `Authorization`, `Cookie`, `Set-Cookie`, `X-CSRFToken`, `secret_key`, `access_token`, `refresh_token` and `password`. The match ignores case, `-` and `_`. For example, `access_token`, `access-token` and `accessToken` all match. The whole key must match. A key that only contains a default name, such as `old_password`, is not hidden.

To change the list of keys:

```python
AUDIT_SENSITIVE_KEYS_DEFAULT = ["authorization", "cookie", "password"]  # replaces the 8 defaults
AUDIT_SENSITIVE_KEYS_EXTRA = ["token", "client_secret"]  # added to the list
```

A value nested more than 64 levels deep becomes `"[TRUNCATED]"`. A cycle also ends in `"[TRUNCATED]"`. Without this limit, the JSON renderer cannot write the line, and the line is lost.

The package reads key names only. It does not scan text. These values are not hidden:

- Outgoing request logs from `HTTPClient`. It writes `request_repr` and `response_repr` as strings, so the package does not see the keys inside them.
- Secrets inside a string, such as an HTML response body or an error message.
- Request bodies that are not JSON. The middleware does not log those bodies.
- Secrets in the URL path, such as `/reset/<token>/`.
- Keys with other names, such as `client_secret`, `id_token` or `new_password`. Add them to `AUDIT_SENSITIVE_KEYS_EXTRA`.
- Values inside dataclass objects. orjson writes them as objects, but the package walks only mappings, lists and tuples.

If a page returns secrets in its body, add a path rule with `"response_target": ["*"]`. It hides the body and keeps the audit record. To drop the record too, add the URL pattern to `AUDIT_UNREGISTERED_URLS_EXTRA`.

### Per-path rules

`AUDIT_PATH_RULES` changes the request log line of chosen paths. It applies only to the line that the middleware writes for an incoming request, not to model, login or `HTTPClient` lines.

```python
AUDIT_PATH_RULES = [
    {
        "path": r"^/client_applications/login/?$",
        "mode": "hash",
        "request_target": ["access_key"],
        "request_headers": ["*"],
    },
    {
        "path": r"^/client_applications/\d+/keys/$",
        "mode": "mask",
        "response_target": ["*"],
    },
    {"path": r"^/health/$", "mode": "skip"},
]
```

| Rule key | Meaning |
|---|---|
| `path` | A regex. A hash or mask rule matches when `re.search` finds it in the request path, without the query string. A skip rule must match the whole path. |
| `mode` | `"hash"` uses `AUDIT_SENSITIVE_VALUE_FUNCTION`. `"mask"` writes `"[MASKED]"`. `"skip"` writes no request log line. |
| `request_target` | Keys whose values are hidden in the request body and the query parameters. `["*"]` hides the whole body and every query value. |
| `response_target` | Keys whose values are hidden in the response body. `["*"]` hides the whole body. |
| `request_headers` | Request header names whose values are hidden. `["*"]` hides every request header value. |
| `response_headers` | Response header names whose values are hidden. `["*"]` hides every response header value. |

- The middleware checks `AUDIT_UNREGISTERED_URLS_*` and `AUDIT_REGISTERED_URLS` first. Then it checks the rules in order, and only the first matching rule applies.
- The URL settings match from the start of the path (`re.match`). Rules match anywhere in it (`re.search`), so add `^` to anchor a rule.
- Keys and header names match like the sensitive keys: at any depth, ignoring case, `-` and `_`.
- On a matched path, the sensitive keys are still hidden, with the rule's mode. A rule cannot make a value visible.
- A skip rule's path must start with `^` and end with `$`, because an unanchored skip can drop the audit record of many paths. A skip rule must also match the whole path. A skip rule has no lists.
- A hash or mask rule needs at least one non-empty list. A rule that hides nothing would only block later rules.
- Key targets reach JSON bodies only. A body that is plain text, such as an HTML page, is hidden only by `"*"`.
- The startup check also rejects an unknown rule key, an invalid regex, and an unknown mode. It also rejects an empty or non-string list entry, and `"*"` together with other entries.

Rules fail open. If a URL changes and its rule stops matching, the rule's targets are logged as they are. Put a key that is secret on every path in `AUDIT_SENSITIVE_KEYS_EXTRA`, and use rules only for keys that are secret on one path. Do not skip a path that reads or changes health data: HIPAA requires a record of that activity.

Put specific paths before general ones: an earlier broad rule wins, and a later rule's targets are then logged as they are. Keep the regexes simple. They run on every request, on paths that clients choose, and a pattern with nested repeats, such as `(a+)+`, can take a long time. For short secrets, `mask` is safer than `hash`, because a person who has the hash key can test guesses. `request_headers: ["*"]` also hides `Content-Type` and `User-Agent`.

### The hash

The built-in hash is HMAC-SHA256 from Django's `salted_hmac`, cut to 16 hex characters. The whole value is hashed as one string. A value that is not a string, such as a list or a number, is hashed as its Python text, `str(value)`. The same value gives the same hash, so you can follow one token across log lines. A person who reads the logs cannot reverse the hash or test guesses without the key.

The key is `AUDIT_HASH_SECRET`, or `SECRET_KEY` if you do not set it. In production, set a separate `AUDIT_HASH_SECRET` and read it from the environment, like your other secrets:

```python
AUDIT_HASH_SECRET = env("AUDIT_HASH_SECRET")
```

- If you change the key, every hash changes.
- Two services give the same hash for a value only if they use the same key.
- A person who has the key can test guesses for short values, such as passwords, because HMAC is fast.
- Two equal values give equal hashes. A log reader can see that two users sent the same password, without seeing the password.
- `None` and `""` stay as they are, so a missing value does not look like a secret.
- If Django settings are not configured, the package cannot read your settings and has no key. It then uses the 8 default keys and writes `"[MASKED]"`.

### Your own value function

To decide yourself what replaces a sensitive value, name a function:

```python
AUDIT_SENSITIVE_VALUE_FUNCTION = "myapp.logging.hide_value"
```

```python
from activity_audit.shared_processors import hash_value


def hide_value(key, value):
    if key.lower() == "password":
        return "[MASKED]"
    return hash_value(key, value)
```

The package calls the function for each matched key, with the original key and the value. The function returns what the log line shows. Return a string, a number, a bool or `None`. The package does not walk the returned value. A dict or list that you return is written as it is, with no hiding inside it. Do not raise an exception from the function, for the same reasons as for processors below.

### Your own processors

```python
AUDIT_PROCESSORS = ["myapp.logging.add_tenant_id"]
```

Each entry is the dotted path to a structlog processor: a function `(logger, method_name, event_dict)` that returns the event dict. The processors run in order, on every log line. They run after the package sets `log_type` and `extra`, and before it hides sensitive values, so a value that a processor adds is hidden too. A processor sees values before they are hidden. Put the values that a processor adds under `extra`. The JSON formatter from `get_stdlib_formatter()` drops top-level keys that are not standard fields. Do not send the event dict anywhere from a processor. Do not raise an exception from a processor. For a structlog logger, the exception goes up into the code that wrote the log line. For a standard `logging` logger, the handler prints the exception to stderr and the line is lost. `structlog.DropEvent` works the other way round: it drops the line for a structlog logger, and a standard `logging` logger raises it into the caller.

## Log Types

### Container Logs
#### Console Log Format
```shell
'%(levelname)s %(asctime)s %(pathname)s %(module)s %(funcName)s %(message)s'
-----------------------------------------------------------------------------
INFO 2025-04-30 08:51:10,403 /app/patients/api/utils.py utils create_patient_with_contacts_and_diseases Patient 'd6c9a056-0b57-453a-8c0f-44319004b761 - Patient3' created.
```

#### File Log Format
### APP Log
```json
{
    "timestamp": "2025-05-15 13:38:02.141",
    "level": "DEBUG",
    "name": "botocore.auth",
    "path": "/opt/venv/lib/python3.11/site-packages/botocore/auth.py",
    "module": "auth",
    "function": "add_auth",
    "message": "Calculating signature using v4 auth.",
    "exception": ""
}
```

### CRUD Log
```json
{
    "timestamp": "2025-08-16 17:06:32.403",
    "level": "AUDIT",
    "name": "audit.model",
    "message": "CREATE event by User (id: 6f77b814-f9c1-4cab-a737-6677734bc303)",
    "request_id": "f3c9a1b2-0001-4abc-beef-deadbeef0001",
    "model": "User",
    "event_type": "CREATE",
    "instance_id": "6f77b814-f9c1-4cab-a737-6677734bc303",
    "instance_repr" : {
        "name": "Test Model",
        "is_active": true,
        "created_at": "2025-08-29T08:18:54Z",
        "updated_at": "2025-08-29T08:18:54Z"
    },
    "user_id": "cae8ffb4-ba52-409c-9a6f-e10362bfaf97",
    "user_info": {
        "title": "mr",
        "email": "example@source.com",
        "first_name": "mohamlal",
        "middle_name": "v",
        "last_name": "nair",
        "sex": "m",
    },
    "extra": {}
}
```

### Request-Response Log
#### Incoming Log Format
```json
{
    "timestamp": "2025-05-19 15:25:27.836",
    "level": "API",
    "name": "audit.request",
    "message": "Audit Internal Request",
    "request_id": "f3c9a1b2-0001-4abc-beef-deadbeef0001",
    "service_name": "my_service",
    "request_type": "internal",
    "protocol": "http",
    "user_id": "14ab1197-ebdd-4300-a618-5910e0219936",
    "user_info": {
        "title": "mr",
        "email": "example@email.com",
        "first_name": "mohanlal",
        "middle_name": "",
        "last_name": "nair",
        "sex": "male",
        "date_of_birth": "21/30/1939"
    },
    "request_repr": {
        "method": "GET",
        "path": "/api/v1/health/",
        "query_params": {},
        "headers": {
            "Content-Type": "application/json",
        },
        "user": null,
        "body": {
            "title": "hello"
        }
    },
    "response_repr": {
        "status_code": 200,
        "headers": {
            "Content-Type": "application/json",
        },
        "body": {
            "status": "ok"
        }
    },
    "error_message": null,
    "execution_time": 5.376734018325806
}
```

#### External Log format
```json
{
    "timestamp": "2025-05-19 15:25:27.717",
    "level": "API",
    "name": "audit.request",
    "message": "Audit External Service",
    "request_id": "f3c9a1b2-0001-4abc-beef-deadbeef0001",
    "service_name": "apollo",
    "request_type": "external",
    "protocol": "http",
    "user_id": "14ab1197-ebdd-4300-a618-5910e0219936",
    "user_info": {
        "title": "mr",
        "email": "example@email.com",
        "first_name": "mohanlal",
        "middle_name": "",
        "last_name": "nair",
        "sex": "male",
        "date_of_birth": "21/30/1939"
    },
    "request_repr": {
        "endpoint": "example.com",
        "method": "GET",
        "headers": {},
        "body": {}
    },
    "response_repr": {
        "status_code": 200,
        "body": {
            "title": "title",
            "expiresIn": 3600,
            "error": "",
            "errorDescription": ""
        }
    },
    "error_message": "",
    "execution_time": 5.16809344291687
}
```

## Notes

- Compatible with **Django 3.2+** and **Python 3.7+**.
- Designed for easy integration with observability stacks using Vector, ClickHouse, and Grafana.
- Capture Django CRUD operations automatically
- Write structured JSON logs
- Ready for production-grade logging pipelines
- Simple pip install, reusable across projects
- Zero additional database overhead! 

## Related Tools

- [Vector.dev](https://vector.dev/)
- [ClickHouse](https://clickhouse.com/)
- [Grafana](https://grafana.com/)

## License

This project is licensed under the MIT License - see the LICENSE file for details.



