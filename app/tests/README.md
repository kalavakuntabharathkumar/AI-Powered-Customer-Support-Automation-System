# Test Suite — AI Customer Support Automation System

This directory contains the full pytest test suite covering the AI services and API endpoints.

---

## Running Tests

### Prerequisites

Ensure you have all dependencies installed:

```bash
pip install -r requirements.txt
```

### Run all tests

```bash
pytest
```

### Run with verbose output

```bash
pytest -v
```

### Run a specific test file

```bash
pytest app/tests/test_intent_classifier.py -v
pytest app/tests/test_response_generator.py -v
pytest app/tests/test_api.py -v
```

### Run a specific test class or test

```bash
pytest app/tests/test_api.py::TestCreateTicket -v
pytest app/tests/test_api.py::TestCreateTicket::test_create_ticket_returns_201 -v
```

---

## Coverage Report

### Run tests with coverage

```bash
pytest --cov=app --cov-report=term-missing
```

### Generate an HTML coverage report

```bash
pytest --cov=app --cov-report=html
```

The HTML report is written to `htmlcov/index.html`. Open it in your browser:

```bash
open htmlcov/index.html    # macOS
xdg-open htmlcov/index.html  # Linux
```

### Enforce a minimum coverage threshold (85%)

```bash
pytest --cov=app --cov-report=term-missing --cov-fail-under=85
```

---

## Test Database

All API tests use an **in-memory SQLite database** (via `aiosqlite`). The test database is
created fresh before each test and torn down after. This keeps tests fast, isolated, and
free from any dependency on a running PostgreSQL instance.

---

## Test Structure

| File | What it tests |
|---|---|
| `test_intent_classifier.py` | Rule-based classifier, AI response parsing, async classify_intent function |
| `test_response_generator.py` | Template selection, confidence-based review flag, tone handling |
| `test_api.py` | All HTTP endpoints — create, retrieve, list, approve tickets, analytics |

---

## Fixtures

| Fixture | Scope | Description |
|---|---|---|
| `client` | function | Async HTTPX client backed by the FastAPI test app |
| `setup_database` | function (autouse) | Creates / drops tables around each test |
| `sample_ticket` | function | Inserts a pre-processed ticket with a response for approval tests |

---

## Notes

- Tests targeting AI service calls (LangChain / OpenAI) use `monkeypatch` to simulate missing API keys, ensuring the fallback paths are exercised without requiring a real key.
- The `pytest-asyncio` plugin is required for all `async def` test functions. Asyncio mode is configured in `pyproject.toml`.
