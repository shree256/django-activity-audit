# Django Activity Audit

A Django package that extends the default logging mechanism to track CRUD operations and container logs.

## Features

- Automatic logging of CRUD operations (Create, Read, Update, Delete)
- Tracks both HTTP requests and model changes
- Custom log levels Audit(21) and API(22) for CRUD and Request-Response auditing.
- Structured JSON logs for audit trails
- Human-readable container logs
- Separate log files for audit and container logs
- Console and file output options

## Installation

1. Install the package:
```bash
pip install django-activity-audit
```

2. Add 'django_activity_audit' to your INSTALLED_APPS in settings.py:
```python
INSTALLED_APPS = [
    ...
    'django_activity_audit',
]
```

3. Add the middleware to your MIDDLEWARE in settings.py:
```python
MIDDLEWARE = [
    ...
    'django_activity_audit.middleware.AuditLoggingMiddleware',
]
```

4. Configure logging in settings.py:
```python
from django_activity_audit import *

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": get_json_formatter(),
        "verbose": get_console_formatter(),
        "api_json": get_api_file_formatter(),
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": get_json_handler(level="DEBUG", formatter="json"),
        "api_file": get_api_file_handler(formatter="api_json"),
    },
    "root": {"level": "DEBUG", "handlers": ["console", "file"]},
    "loggers": {
        "audit.request": {
            "handlers": ["api_file"],
            "level": "API",
            "propagate": False,
        },
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    }
}
```

5. For external services logging, extend ```HTTPClient or SFTPClient```
```python
class ExternalService(HTTPClient):
    def __init__(self):
        super().__init__("service_name")

    def connect(self):
        url = "https://www.sample.com"
        response = self.get(url) # sample log structure below
```

7. Create ```audit_logs``` folder in project directory

## Log Types

### Container Logs
#### Console Log Format
```shell
'%(levelname)s %(asctime)s %(pathname)s %(module)s %(funcName)s %(message)s'
-----------------------------------------------------------------------------
INFO 2025-04-30 08:51:10,403 /app/patients/api/utils.py utils create_patient_with_contacts_and_diseases Patient 'd6c9a056-0b57-453a-8c0f-44319004b761 - Patient3' created.
```

#### File Log Format
```json
{
    "timestamp": "2025-05-15 13:38:02.141",
    "level": "DEBUG",
    "name": "botocore.auth",
    "path": "/opt/venv/lib/python3.11/site-packages/botocore/auth.py",
    "module": "auth",
    "function": "add_auth",
    "message": "Calculating signature using v4 auth.",
    "exception": "",
    "request": "",
    "extra_fields": ""
}
```

### CRUD Log
```json
{
    "timestamp": "2025-08-16 17:06:32.403",
    "level": "AUDIT",
    "name": "audit.crud",
    "message": "CREATE event for User (id: 6f77b814-f9c1-4cab-a737-6677734bc303)",
    "model": "User",
    "event_type": "CREATE",
    "instance_id": "6f77b814-f9c1-4cab-a737-6677734bc303",
    "user": {
        "id": "cae8ffb4-ba52-409c-9a6f-e10362bfaf97",
        "title": "",
        "email": "example@source.com",
        "first_name": "",
        "middle_name": "",
        "last_name": "",
        "sex": "",
        "date_of_birth": null
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
    "service_name": "review_board",
    "request_type": "internal",
    "protocol": "http",
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
    "service_name": "apollo",
    "request_type": "external",
    "protocol": "http",
    "request_repr": "{'endpoint': 'https://www.sample.com', 'method': 'GET', 'headers': {}, 'body': {}}",
    "response_repr": "{'status_code': 200, 'body': {'title': 'title', 'expiresIn': 3600, 'error': None, 'errorDescription': None}}",
    "error_message": "",
    "execution_time": 5.16809344291687
}
```
## Project Structure
```text
    django_activity_audit/
        __init__.py
        apps.py
        constants.py
        logging.py
        middleware.py
        signals.py
        handlers.py
        utils.py
        tests.py
    setup.py
    README.md
    LICENSE
    MANIFEST.in
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

- `Vector.dev <https://vector.dev/>`_
- `ClickHouse <https://clickhouse.com/>`_ 
- `Grafana <https://grafana.com/>`_

## License

This project is licensed under the MIT License - see the LICENSE file for details.



