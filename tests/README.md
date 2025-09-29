# Django Activity Audit Test Setup

This directory contains a complete Django test application to test the `django-activity-audit` package.

## Structure

- `publications/` - Test Django app with Book and Author models
- `test_audit.py` - Test cases for auditing functionality
- `test_settings.py` - Django settings for testing
- `manage.py` - Django management script
- `urls.py` - URL configuration with REST API endpoints

## Models

### Author
- `name` - CharField (max_length=100)
- `experience` - TextField
- `created_at` - DateTimeField (auto_now_add=True)
- `updated_at` - DateTimeField (auto_now=True)

### Book
- `title` - CharField (max_length=200)
- `author` - ForeignKey to Author
- `created_at` - DateTimeField (auto_now_add=True)
- `updated_at` - DateTimeField (auto_now=True)

## Test Cases

1. **ModelOperationsTest** - Tests model creation and update logging
   - `test_model_creation_logging()` - Verifies creation events are logged
   - `test_model_update_logging()` - Verifies update events are logged

2. **APIRequestTest** - Tests API request logging
   - `test_api_request_logging()` - Verifies API requests are logged
   - `test_audit_folder_structure()` - Verifies logs are generated in audit folder

## Running Tests

From the project root:

```bash
# Run all tests
make test

# Run with pytest
make test-quick

# Run specific test types
make test-models
make test-requests

# Run with coverage
make test-coverage
```

## API Endpoints

- `GET /api/books/` - List all books
- `POST /api/books/` - Create a new book
- `PUT /api/books/{id}/` - Update a book
- `GET /api/authors/` - List all authors
- `POST /api/authors/` - Create a new author
- `PUT /api/authors/{id}/` - Update an author

## Audit Configuration

The test setup is configured to log:
- Model creation and updates for Book and Author models
- API requests (GET, POST, PUT)
- Logs are written to `tests/audit/` directory in JSON format
