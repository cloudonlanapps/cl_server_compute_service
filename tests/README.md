# Tests for Compute Service

This directory contains the test suite for the compute microservice. The tests cover job management, worker capabilities, authentication, and integration workflows using `pytest`.

## Overview & Structure

The test suite is organized into two categories:

- **Unit tests** (`test_*.py`) — Test individual components with in-memory SQLite databases and mocked dependencies
- **Integration tests** (`test_integration.py`) — Test end-to-end workflows with full service integration

## Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- Dependencies installed via `uv sync`

**Note:** With uv, you don't need to manually create or activate virtual environments. Use `uv run` to execute commands in the automatically managed environment.

## Running Tests

### Run All Tests

To run the entire test suite with coverage:

```bash
uv run pytest
```

**Coverage requirement:** 90% (configured in `pyproject.toml`)

### Run Specific Test Files

To run tests from a specific file:

```bash
uv run pytest tests/test_routes.py -v
uv run pytest tests/test_service.py -v
uv run pytest tests/test_worker.py -v
```

### Run Individual Tests

To run a specific test function:

```bash
uv run pytest tests/test_routes.py::test_get_job -v

# Or specific test in a class
uv run pytest tests/test_service.py::TestJobService::test_create_job -v
```

### Coverage Options

**Default behavior:** Coverage is automatically collected with HTML + terminal reports and requires ≥90% coverage.

```bash
# Run tests with coverage (generates htmlcov/ directory + terminal report)
uv run pytest

# Skip coverage for quick testing
uv run pytest --no-cov

# Override coverage threshold (e.g., for debugging)
uv run pytest --cov-fail-under=0
```

Coverage reports are saved to `htmlcov/index.html` - open this file in a browser to view detailed coverage.

## Test Structure

The tests are organized into the following files:

| File | Description |
|------|-------------|
| `tests/test_routes.py` | API endpoint tests (GET, DELETE, admin endpoints) |
| `tests/test_service.py` | Business logic tests (JobService, CapabilityService) |
| `tests/test_worker.py` | Worker execution and job processing tests |
| `tests/test_capability.py` | Worker capability discovery and MQTT tests |
| `tests/test_database.py` | Database operations and migration tests |
| `tests/test_auth.py` | Authentication and authorization tests |
| `tests/test_integration.py` | End-to-end integration tests |
| `tests/conftest.py` | Pytest fixtures for database sessions and test clients |

## Configuration

The test configuration is defined in `pyproject.toml` under `[tool.pytest.ini_options]`:
- **Test Paths**: `tests`
- **Coverage**: Automatically enabled with HTML + terminal reports
- **Coverage Threshold**: 90% minimum (tests fail if below)
- **Asyncio Mode**: Auto-detection for async tests
- **Markers**: `integration` for integration tests

## Quick Reference

For a quick command reference, see [QUICK.md](QUICK.md).
