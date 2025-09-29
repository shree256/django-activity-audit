build:
	rm -rf dist/ build/
	hatch build

publish:
	hatch publish

install:
	pip install .[dev]

# Test commands
test:
	uv run pytest tests/ -v

test-coverage:
	uv run pytest tests/ --cov=activity_audit --cov-report=html --cov-report=term

test-quick:
	uv run pytest tests/ -v -x

test-models:
	uv run pytest tests/ -k "test_model" -v

test-requests:
	uv run pytest tests/ -k "test_http_request or test_api_request" -v

# Database setup for tests
migrate:
	python3 tests/manage.py migrate --settings=tests.test_settings

makemigrations:
	python3 tests/manage.py makemigrations publications --settings=tests.test_settings

# Clean up
clean-logs:
	rm -rf tests/audit/*

clean-db:
	rm -f tests/db_test.sqlite3

clean: clean-logs clean-db
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf dist/
	rm -rf build/