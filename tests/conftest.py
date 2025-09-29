import pytest
import os
import django


def pytest_configure():
    """Configure Django settings for pytest."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.test_settings")
    django.setup()


@pytest.fixture
def api_client():
    """Create an API client for testing."""
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def author_data():
    """Sample author data for testing."""
    return {
        "name": "Test Author",
        "experience": "Experienced writer with 10 years in publishing",
    }


@pytest.fixture
def book_data(author_data):
    """Sample book data for testing."""
    return {
        "title": "Test Book",
        "author": 1,  # Will be set after author creation
    }
