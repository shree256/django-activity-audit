# User Activity Feed — Implementation Plan

## Background

The current `django-activity-audit` package captures a **technical/compliance audit trail** of all model CRUD events, writing structured JSON logs to files that flow through Vector into ClickHouse and are visualized in Grafana.

The goal here is to add a **user-facing activity feed** — shown in a UI dashboard — that displays human-readable entries like:

> "User X edited Patient John Doe"

---

## Should User Activity Logs Be Separate?

**Yes.** They serve fundamentally different purposes:

| Dimension | Current Audit Logs | User Activity Feed |
|---|---|---|
| **Purpose** | Compliance, ops, debugging | End-user-facing dashboard |
| **Volume** | Every model event (high) | Selective, meaningful actions only |
| **Format** | Raw field snapshot (`instance_repr`) | Human-readable + field-level diff |
| **Consumer** | ClickHouse / Grafana | App UI via REST API |
| **Query pattern** | Analytics aggregations | Paginated feed per user/entity |
| **Entity name** | Not stored (only ID) | `str(instance)` e.g. "Patient John Doe" |
| **Changed fields** | Full snapshot, no diff | `{field: {from: X, to: Y}}` |

The existing audit pipeline remains **untouched**. The new activity feed runs alongside it as a separate logger, separate log file, separate ClickHouse table, and separate Vector pipeline.

---

## Architecture

### Flow

```
Model Signal (save/delete/m2m)
        │
        ├──► audit.model logger ──► audit.log ──► Vector ──► emr_logs.audit       (unchanged)
        │
        └──► audit.activity logger ──► activity.log ──► Vector ──► emr_logs.user_activity  (new)
```

### What Makes the Activity Log Different

1. **Opt-in models only** — controlled by `ACTIVITY_REGISTERED_MODELS` setting. Only meaningful user-facing models (e.g. `patients.Patient`, `appointments.Appointment`) generate activity entries.
2. **Field-level diff for UPDATE** — captures what actually changed, not just the full post-save snapshot.
3. **Entity name** — calls `str(instance)` to store a human-readable label alongside the ID.
4. **No PRE\_\* events** — only `CREATE`, `UPDATE`, `DELETE` (and optionally `BULK_*`, `M2M`).

---

## Implementation

### Part 1 — Package Changes (`activity_audit/`)

#### 1.1 New setting: `ACTIVITY_REGISTERED_MODELS`

In `activity_audit/settings.py`, add:

```python
# Opt-in list of models to include in the user activity feed.
# Format: ["app_label.ModelName", ...]
# If empty, no activity feed entries are generated.
ACTIVITY_REGISTERED_MODELS = getattr(settings, "ACTIVITY_REGISTERED_MODELS", [])
```

#### 1.2 Pre-save snapshot for diff computation

In `signals.py`, before calling the original `save()`, capture the old field values for existing instances:

```python
def get_pre_save_snapshot(instance: models.Model) -> dict:
    """Fetch the current DB state before save to compute a diff."""
    if instance._state.adding or not instance.pk:
        return {}
    try:
        db_instance = instance.__class__._default_manager.get(pk=instance.pk)
        return instance_to_dict(db_instance)
    except instance.__class__.DoesNotExist:
        return {}
```

#### 1.3 Field-level diff computation

```python
def compute_diff(pre: dict, post: dict) -> dict:
    """Return only the fields that changed, with before/after values."""
    return {
        field: {"from": pre[field], "to": post[field]}
        for field in post
        if field in pre and pre[field] != post[field]
    }
```

#### 1.4 New `push_activity_log` function

Separate from `push_log`. Writes to `audit.activity` logger:

```python
activity_logger = logging.getLogger("audit.activity")

def push_activity_log(
    action: str,           # "CREATED" | "EDITED" | "DELETED"
    entity_type: str,      # "Patient"
    entity_id: str,
    entity_name: str,      # str(instance)
    changed_fields: dict,  # {field: {from, to}} — empty for CREATE/DELETE
    extra: dict = {},
) -> None:
    try:
        user_id, user_info = get_user_details()
        payload = {
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "entity_name": entity_name,
            "changed_fields": changed_fields,
            "user_id": user_id,
            "user_info": user_info,
            "extra": extra,
        }

        def safe_activity_log():
            try:
                activity_logger.activity(
                    f"{action} event on {entity_type} ({entity_name})",
                    extra=payload,
                )
            except Exception as e:
                activity_logger.error(f"Failed to write activity log: {e}")

        transaction.on_commit(safe_activity_log)
    except Exception as e:
        activity_logger.error(f"Failed to prepare activity log: {e}")
```

#### 1.5 New `ActivityFormatter` in `formatters.py`

```python
class ActivityFormatter(logging.Formatter):
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

        activity_fields = [
            "action",
            "entity_type",
            "entity_id",
            "entity_name",
            "changed_fields",
            "user_id",
            "user_info",
            "extra",
        ]

        for field in activity_fields:
            log_data[field] = getattr(record, field, "")

        return json.dumps(log_data, default=_json_default)
```

#### 1.6 New `activity` log level

In `logger_levels.py`, add an `ACTIVITY` level (e.g. integer `17`, below `AUDIT` at `18`):

```python
ACTIVITY_LEVEL = 17
logging.addLevelName(ACTIVITY_LEVEL, "ACTIVITY")

def activity(self, message, *args, **kwargs):
    if self.isEnabledFor(ACTIVITY_LEVEL):
        self._log(ACTIVITY_LEVEL, message, args, **kwargs)

logging.Logger.activity = activity
```

---

### Part 2 — ClickHouse Table

```sql
CREATE TABLE emr_logs.user_activity
(
    `timestamp`       DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    `ingest_time`     DateTime('UTC') DEFAULT now() CODEC(Delta, ZSTD),

    `level`           LowCardinality(String) CODEC(ZSTD),
    `name`            LowCardinality(String) CODEC(ZSTD),
    `message`         String CODEC(ZSTD),

    `service_name`    LowCardinality(String) CODEC(ZSTD),

    `user_id`         String CODEC(ZSTD),
    `user_info`       String CODEC(ZSTD),    -- JSON serialized

    `action`          LowCardinality(String) CODEC(ZSTD),   -- CREATED | EDITED | DELETED
    `entity_type`     LowCardinality(String) CODEC(ZSTD),   -- "Patient"
    `entity_id`       String CODEC(ZSTD),
    `entity_name`     String CODEC(ZSTD),                   -- "John Doe"
    `changed_fields`  String CODEC(ZSTD),   -- JSON: {field: {from: X, to: Y}}
    `extra`           String CODEC(ZSTD)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, ingest_time, user_id, entity_type)
SETTINGS index_granularity = 8192;
```

---

### Part 3 — Vector Configuration (additions to `vector.yaml`)

```yaml
sources:
  activity_logs:
    type: file
    include:
      - "/app/audit/activity.log"
      - "/app/audit/activity.log.*"
    read_from: beginning
    start_at_beginning: false
    ignore_older_secs: 604800
    fingerprinting:
      strategy: "device_and_inode"
    max_line_bytes: 10485760

transforms:
  parse_activity_logs:
    type: remap
    inputs:
      - activity_logs
    source: |
      parsed, err = parse_json(.message)
      if err == null {
        .timestamp      = parsed.timestamp
        .level          = parsed.level
        .name           = parsed.name
        .message        = parsed.message
        .service_name   = parsed.service_name
        .user_id        = parsed.user_id
        .user_info      = if is_object(parsed.user_info) || is_array(parsed.user_info) { encode_json(parsed.user_info) } else { parsed.user_info }
        .action         = parsed.action
        .entity_type    = parsed.entity_type
        .entity_id      = parsed.entity_id
        .entity_name    = parsed.entity_name
        .changed_fields = if is_object(parsed.changed_fields) || is_array(parsed.changed_fields) { encode_json(parsed.changed_fields) } else { parsed.changed_fields }
        .extra          = if is_object(parsed.extra) || is_array(parsed.extra) { encode_json(parsed.extra) } else { parsed.extra }
        del(.file)
        del(.host)
        del(.source_type)
        del(.extra_fields)
      }

sinks:
  clickhouse_user_activity:
    type: clickhouse
    inputs:
      - parse_activity_logs
    endpoint: "${CLICKHOUSE_ENDPOINT}"
    database: "emr_logs"
    table: "user_activity"
    auth:
      strategy: "basic"
      user: "${CLICKHOUSE_USER}"
      password: "${CLICKHOUSE_PASSWORD}"
    batch:
      max_events: 1000
      timeout_secs: 30
      max_bytes: 10485760
    request:
      retry_attempts: 3
      retry_backoff_secs: 1
      timeout_secs: 60
```

---

### Part 4 — Django Logging Config (addition to `LOGGING` setting)

```python
LOGGING = {
    "formatters": {
        # ... existing formatters ...
        "activity": {
            "()": "activity_audit.formatters.ActivityFormatter",
        },
    },
    "handlers": {
        # ... existing handlers ...
        "activity_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "audit_logs/activity.log",
            "formatter": "activity",
            "level": "ACTIVITY",  # integer 17
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
        },
    },
    "loggers": {
        # ... existing loggers ...
        "audit.activity": {
            "handlers": ["activity_file"],
            "level": "ACTIVITY",
            "propagate": False,
        },
    },
}
```

---

### Part 5 — UI API Endpoint (in your app)

A DRF view that queries ClickHouse directly and returns a paginated activity feed:

```
GET /api/v1/activity-feed/
    ?user_id=<uuid>
    &entity_type=Patient
    &entity_id=<uuid>
    &from=2025-01-01
    &to=2025-12-31
    &page=1
    &page_size=20
```

**Sample response:**

```json
{
  "count": 142,
  "results": [
    {
      "timestamp": "2025-10-01 14:32:10.442",
      "user": {
        "id": "cae8ffb4-ba52-409c-9a6f-e10362bfaf97",
        "first_name": "Mohanlal",
        "last_name": "Nair",
        "email": "mohanlal@example.com"
      },
      "action": "EDITED",
      "entity_type": "Patient",
      "entity_id": "6f77b814-f9c1-4cab-a737-6677734bc303",
      "entity_name": "John Doe",
      "changed_fields": {
        "date_of_birth": { "from": "1990-01-01", "to": "1990-01-15" },
        "phone": { "from": "555-0100", "to": "555-0199" }
      }
    }
  ]
}
```

---

## Sample Activity Log Entry

```json
{
    "timestamp": "2025-10-01 14:32:10.442",
    "level": "ACTIVITY",
    "name": "audit.activity",
    "message": "EDITED event on Patient (John Doe)",
    "service_name": "review_board",
    "user_id": "cae8ffb4-ba52-409c-9a6f-e10362bfaf97",
    "user_info": {
        "email": "mohanlal@example.com",
        "first_name": "Mohanlal",
        "last_name": "Nair"
    },
    "action": "EDITED",
    "entity_type": "Patient",
    "entity_id": "6f77b814-f9c1-4cab-a737-6677734bc303",
    "entity_name": "John Doe",
    "changed_fields": {
        "date_of_birth": { "from": "1990-01-01", "to": "1990-01-15" },
        "phone": { "from": "555-0100", "to": "555-0199" }
    },
    "extra": {}
}
```

---

## Summary

| | Current Audit Logs | New User Activity Logs |
|---|---|---|
| **Keep?** | Yes, unchanged | New addition |
| **Logger name** | `audit.model` | `audit.activity` |
| **Log file** | `audit.log` | `activity.log` |
| **Models covered** | All (minus `UNREGISTERED_CLASSES`) | Opt-in via `ACTIVITY_REGISTERED_MODELS` |
| **ClickHouse table** | `emr_logs.audit` | `emr_logs.user_activity` |
| **PRE\_\* events** | Yes | No |
| **Changed fields** | Not computed | Field-level diff |
| **Entity name** | Not stored | `str(instance)` |
| **Consumer** | Grafana / ops | App dashboard UI |
| **Human-readable** | No | Yes |

---

## Future Scope

- **Grouping**: Collapse rapid edits by the same user on the same entity into a single activity entry.
- **Action labels**: Support custom human-readable action strings per model (e.g. `"discharged"` instead of `"EDITED"` for a specific status field change).
- **Async ingestion**: Use `QueueHandler` + `QueueListener` to push activity logs off the request thread.
