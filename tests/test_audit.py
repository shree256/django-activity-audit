import json
from pathlib import Path

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from tests.publications.models import Author, Book


@pytest.mark.django_db
class TestModelOperations:
    """Test 1 & 2: Check model creation and update logging"""

    @pytest.fixture(autouse=True)
    def setup_audit_dir(self):
        """Set up audit directory for each test."""
        self.audit_dir = Path("tests/audit")
        self.audit_dir.mkdir(exist_ok=True)

    def test_model_creation_logging(self):
        """Test that model creation is properly logged"""
        # Create an author
        author = Author.objects.create(
            name="Test Author",
            experience="Experienced writer with 10 years in publishing",
        )

        # Create a book
        book = Book.objects.create(title="Test Book", author=author)

        # Force flush of all loggers
        import logging

        for handler in logging.getLogger("audit.model").handlers:
            handler.flush()

        # Check that audit logs were created
        log_files = list(self.audit_dir.glob("*.jsonl"))
        assert len(log_files) > 0, "No audit log files found"

        # Read and verify the logs
        creation_logs_found = 0
        for log_file in log_files:
            with open(log_file, "r") as f:
                for line in f:
                    if line.strip():
                        log_entry = json.loads(line)
                        if log_entry.get("event_type") == "CREATE" and log_entry.get(
                            "model"
                        ) in ["Author", "Book"]:
                            creation_logs_found += 1

        assert creation_logs_found >= 2, (
            f"Expected at least 2 creation logs, found {creation_logs_found}"
        )

    def test_model_update_logging(self):
        """Test that model updates are properly logged"""
        # Create initial objects
        author = Author.objects.create(
            name="Original Author", experience="Original experience"
        )

        book = Book.objects.create(title="Original Title", author=author)

        # Update the author
        author.experience = "Updated experience with new skills"
        author.save()

        # Update the book
        book.title = "Updated Book Title"
        book.save()

        # Force flush of all loggers
        import logging

        for handler in logging.getLogger("audit.model").handlers:
            handler.flush()

        # Check that update logs were created
        log_files = list(self.audit_dir.glob("*.jsonl"))
        assert len(log_files) > 0, "No audit log files found after updates"

        # Read and verify the update logs
        update_logs_found = 0
        for log_file in log_files:
            with open(log_file, "r") as f:
                for line in f:
                    if line.strip():
                        log_entry = json.loads(line)
                        if log_entry.get("event_type") == "UPDATE" and log_entry.get(
                            "model"
                        ) in ["Author", "Book"]:
                            update_logs_found += 1

        assert update_logs_found >= 2, (
            f"Expected at least 2 update logs, found {update_logs_found}"
        )


@pytest.mark.django_db
class TestAPIRequests:
    """Test 3: Check API request logging"""

    @pytest.fixture(autouse=True)
    def setup_test(self):
        """Set up test environment."""
        self.client = APIClient()
        self.audit_dir = Path("tests/audit")
        self.audit_dir.mkdir(exist_ok=True)

    def test_api_request_logging(self):
        """Test that API requests are properly logged"""
        # Create test data
        author = Author.objects.create(
            name="API Test Author", experience="Test experience for API"
        )

        book = Book.objects.create(title="API Test Book", author=author)

        # Make API requests
        # GET request
        response = self.client.get("/api/books/")
        assert response.status_code == status.HTTP_200_OK

        # POST request
        new_book_data = {"title": "New API Book", "author": author.id}
        response = self.client.post("/api/books/", new_book_data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        # PUT request
        update_data = {"title": "Updated API Book Title", "author": author.id}
        response = self.client.put(f"/api/books/{book.id}/", update_data, format="json")
        assert response.status_code == status.HTTP_200_OK

        # Force flush of all loggers
        import logging

        for handler in logging.getLogger("audit.request").handlers:
            handler.flush()

        # Check that API request logs were created
        log_files = list(self.audit_dir.glob("*.jsonl"))
        assert len(log_files) > 0, "No audit log files found after API requests"

        # Read and verify the API request logs
        api_logs_found = 0
        for log_file in log_files:
            with open(log_file, "r") as f:
                for line in f:
                    if line.strip():
                        log_entry = json.loads(line)
                        if log_entry.get("name") == "audit.request" and log_entry.get(
                            "request_repr", {}
                        ).get("method") in ["GET", "POST", "PUT"]:
                            api_logs_found += 1

        assert api_logs_found >= 3, (
            f"Expected at least 3 API request logs, found {api_logs_found}"
        )

    def test_audit_folder_structure(self):
        """Test that logs are generated in the audit folder"""
        # Make a simple API request
        response = self.client.get("/api/authors/")
        assert response.status_code == status.HTTP_200_OK

        # Force flush of all loggers
        import logging

        for handler in logging.getLogger("audit.request").handlers:
            handler.flush()

        # Check that audit directory exists and contains log files
        assert self.audit_dir.exists(), "Audit directory does not exist"

        log_files = list(self.audit_dir.glob("*.jsonl"))
        assert len(log_files) > 0, "No log files found in audit directory"

        # Verify log file content is valid JSON
        for log_file in log_files:
            with open(log_file, "r") as f:
                for line_num, line in enumerate(f, 1):
                    if line.strip():
                        try:
                            json.loads(line)
                        except json.JSONDecodeError as e:
                            pytest.fail(
                                f"Invalid JSON in {log_file} at line {line_num}: {e}"
                            )


@pytest.mark.django_db
class TestLogFileContents:
    """Test log file contents and structure"""

    @classmethod
    def setup_class(cls):
        """Set up audit directory for these tests."""
        audit_dir = Path("tests/audit")
        audit_dir.mkdir(exist_ok=True)

    @pytest.fixture(autouse=True)
    def setup_audit_dir(self):
        """Set up audit directory for each test."""
        self.audit_dir = Path("tests/audit")
        self.audit_dir.mkdir(exist_ok=True)

    def test_model_log_file_contents(self):
        """Test that model log files contain properly structured JSON with expected fields"""
        # Create test data to generate logs
        author = Author.objects.create(
            name="Log Content Test Author", experience="Testing log file contents"
        )

        book = Book.objects.create(title="Log Content Test Book", author=author)

        # Update to generate update logs
        author.experience = "Updated for log content testing"
        author.save()

        # Force flush of all loggers
        import logging

        for handler in logging.getLogger("audit.model").handlers:
            handler.flush()

        # Check audit.jsonl file structure
        audit_file = self.audit_dir / "audit.jsonl"
        assert audit_file.exists(), "audit.jsonl file should exist"

        log_entries = []
        with open(audit_file, "r") as f:
            for line in f:
                if line.strip():
                    log_entries.append(json.loads(line))

        assert len(log_entries) > 0, "Should have at least one log entry"

        # Verify log entry structure
        for entry in log_entries:
            # Check required fields for model audit logs
            assert "timestamp" in entry, "Log entry should have timestamp"
            assert "level" in entry, "Log entry should have level"
            assert "name" in entry, "Log entry should have name"
            assert "message" in entry, "Log entry should have message"

            # Check audit-specific fields
            if entry.get("name") == "audit.model":
                assert "model" in entry, "Model log should have model field"
                assert "event_type" in entry, "Model log should have event_type field"
                assert "instance_id" in entry, "Model log should have instance_id field"
                assert "instance_repr" in entry, (
                    "Model log should have instance_repr field"
                )
                assert "user_id" in entry, "Model log should have user_id field"
                assert "user_info" in entry, "Model log should have user_info field"
                assert "extra" in entry, "Model log should have extra field"

        # Verify we have the expected event types
        event_types = [
            entry.get("event_type")
            for entry in log_entries
            if entry.get("name") == "audit.model"
        ]
        expected_events = ["PRE_CREATE", "CREATE", "UPDATE"]

        for expected_event in expected_events:
            assert expected_event in event_types, (
                f"Should have {expected_event} event in logs"
            )

        # Verify model names
        models = [
            entry.get("model")
            for entry in log_entries
            if entry.get("name") == "audit.model"
        ]
        assert "Author" in models, "Should have Author model logs"
        assert "Book" in models, "Should have Book model logs"

        # Verify instance_repr contains expected data
        author_logs = [
            entry
            for entry in log_entries
            if entry.get("model") == "Author" and entry.get("event_type") == "CREATE"
        ]
        assert len(author_logs) > 0, "Should have Author creation logs"

        # Find our specific test author in the logs
        test_author_log = None
        for log in author_logs:
            instance_repr = log.get("instance_repr", {})
            if instance_repr.get("name") == "Log Content Test Author":
                test_author_log = log
                break

        assert test_author_log is not None, (
            "Should find our specific test author in logs"
        )
        instance_repr = test_author_log.get("instance_repr", {})
        assert instance_repr.get("name") == "Log Content Test Author", (
            "Instance repr should contain correct author name"
        )
        assert instance_repr.get("experience") == "Testing log file contents", (
            "Instance repr should contain correct experience"
        )

    def test_api_log_file_contents(self):
        """Test that API log files contain properly structured JSON with expected fields"""
        client = APIClient()

        # Create test data
        author = Author.objects.create(
            name="API Log Content Test Author",
            experience="Testing API log file contents",
        )

        # Make various API requests
        response = client.get("/api/authors/")
        assert response.status_code == status.HTTP_200_OK

        new_author_data = {"name": "New API Author", "experience": "Created via API"}
        response = client.post("/api/authors/", new_author_data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        # Force flush of all loggers
        import logging

        for handler in logging.getLogger("audit.request").handlers:
            handler.flush()

        # Check api.jsonl file structure
        api_file = self.audit_dir / "api.jsonl"
        assert api_file.exists(), "api.jsonl file should exist"

        log_entries = []
        with open(api_file, "r") as f:
            for line in f:
                if line.strip():
                    log_entries.append(json.loads(line))

        assert len(log_entries) > 0, "Should have at least one API log entry"

        # Verify log entry structure
        for entry in log_entries:
            # Check required fields for API audit logs
            assert "timestamp" in entry, "API log entry should have timestamp"
            assert "level" in entry, "API log entry should have level"
            assert "name" in entry, "API log entry should have name"
            assert "message" in entry, "API log entry should have message"

            # Check API-specific fields
            if entry.get("name") == "audit.request":
                assert "service_name" in entry, "API log should have service_name field"
                assert "request_type" in entry, "API log should have request_type field"
                assert "protocol" in entry, "API log should have protocol field"
                assert "user_id" in entry, "API log should have user_id field"
                assert "user_info" in entry, "API log should have user_info field"
                assert "request_repr" in entry, "API log should have request_repr field"
                assert "response_repr" in entry, (
                    "API log should have response_repr field"
                )
                assert "error_message" in entry, (
                    "API log should have error_message field"
                )
                assert "execution_time" in entry, (
                    "API log should have execution_time field"
                )

        # Verify we have the expected HTTP methods
        api_logs = [
            entry for entry in log_entries if entry.get("name") == "audit.request"
        ]
        methods = [entry.get("request_repr", {}).get("method") for entry in api_logs]

        assert "GET" in methods, "Should have GET request logs"
        assert "POST" in methods, "Should have POST request logs"

        # Verify request_repr structure
        get_logs = [
            entry
            for entry in api_logs
            if entry.get("request_repr", {}).get("method") == "GET"
        ]
        assert len(get_logs) > 0, "Should have GET request logs"

        get_log = get_logs[0]
        request_repr = get_log.get("request_repr", {})
        assert "method" in request_repr, "Request repr should have method"
        assert "path" in request_repr, "Request repr should have path"
        assert "query_params" in request_repr, "Request repr should have query_params"
        assert "headers" in request_repr, "Request repr should have headers"

        # Verify response_repr structure
        response_repr = get_log.get("response_repr", {})
        assert "headers" in response_repr, "Response repr should have headers"

        # Verify execution_time is a number
        assert isinstance(get_log.get("execution_time"), (int, float)), (
            "Execution time should be a number"
        )
        assert get_log.get("execution_time") >= 0, (
            "Execution time should be non-negative"
        )
