Audit Logging
===================

A Django package that extends the default logging mechanism to track CRUD operations and container logs.

Features
--------

- Automatic logging of CRUD operations (Create, Read, Update, Delete)
- Tracks both HTTP requests and model changes
- Custom AUDIT log level (15) between DEBUG and WARNING
- Structured JSON logs for audit trails
- Human-readable container logs
- Configurable log rotation
- Separate log files for audit and container logs
- Console and file output options

Installation
------------

1. Install the package::

    pip install audit-logging

2. Add ``audit_logging`` to your ``INSTALLED_APPS`` in ``settings.py``::

    INSTALLED_APPS = [
        ...
        'audit_logging',
    ]

3. Add the middleware to your ``MIDDLEWARE`` in ``settings.py``::

    MIDDLEWARE = [
        ...
        'audit_logging.middleware.AuditUserMiddleware',
    ]

4. Configure logging in ``settings.py``::

    from audit_logging.logging_config import get_logging_config

    # Basic configuration
    LOGGING = get_logging_config()

    # Advanced configuration with custom settings
    LOGGING = get_logging_config(
        audit_log_file="logs/audit.log",      # Path to audit log file
        container_log_file="logs/container.log",  # Path to container log file
        console_output=True,                  # Enable console output
        audit_log_level=15,                   # Custom log level for audit logs
        container_log_level=logging.INFO,     # Log level for container logs
        log_rotation={                        # Optional log rotation settings
            "maxBytes": 10485760,             # 10MB
            "backupCount": 5,
        }
    )

Log Types
---------

**Audit Logs**

- JSON formatted
- Contains CRUD operation details
- Includes user information and model changes
- Stored in ``audit.log`` by default

Example audit log entry::

    {
      "timestamp": "2024-04-27T08:25:30.123456",
      "level": "AUDIT",
      "logger": "audit_logger",
      "message": "Model created: User",
      "event_type": "CREATE",
      "model": "auth.User",
      "pk": 123,
      "fields": {
        "username": "john_doe",
        "email": "john@example.com"
      },
      "user": "admin",
      "source": "audit"
    }

**Container Logs**

- Human-readable format
- Contains Django application logs
- Includes request/response information
- Stored in ``container.log`` by default

Example container log entry::

    [2024-04-27 08:25:30] INFO [django.server] "GET /api/users/ HTTP/1.1" 200 1234
    [2024-04-27 08:25:31] WARNING [django.request] Not Found: /api/nonexistent/

Advanced Configuration
----------------------

**Custom Log Rotation**

::

    LOGGING = get_logging_config(
        log_rotation={
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
            "encoding": "utf-8",
        }
    )

**Disable File Logging**

::

    LOGGING = get_logging_config(
        audit_log_file=None,      # Disable audit log file
        container_log_file=None,  # Disable container log file
        console_output=True,      # Only console output
    )

**Different Log Levels**

::

    LOGGING = get_logging_config(
        audit_log_level=15,           # AUDIT level for audit logs
        container_log_level=logging.DEBUG,  # DEBUG level for container logs
    )

Contributing
------------

Contributions are welcome! Please feel free to submit a Pull Request.

License
-------

This project is licensed under the MIT License - see the LICENSE file for details.

Project Structure
-----------------

::

    audit_logging/
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

Notes
-----

- Compatible with **Django 3.2+** and **Python 3.7+**.
- Designed for easy integration with observability stacks using Vector, ClickHouse, and Grafana.

Related Tools
-------------

- `Vector.dev <https://vector.dev/>`_
- `ClickHouse <https://clickhouse.com/>`_
- `Grafana <https://grafana.com/>`_

Summary
-------

- Capture Django CRUD operations automatically
- Write structured JSON logs
- Ready for production-grade logging pipelines
- Simple pip install, reusable across projects
- Zero additional database overhead! 