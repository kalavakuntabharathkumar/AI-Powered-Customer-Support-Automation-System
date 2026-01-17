# Changelog

All notable changes to the AI-Powered Customer Support Automation System are documented here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions
and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] — 2026-01-17

### Added

#### Core AI Services
- **Intent classifier** (`services/intent_classifier.py`): LangChain + OpenAI GPT-3.5-turbo classifier supporting 7 categories — billing, technical, account, general_inquiry, complaint, feature_request, unknown
- **Rule-based fallback classifier**: keyword-pattern matching that activates when the OpenAI API is unavailable or returns an error; returns `used_fallback: true` so callers can distinguish AI vs rule-based results
- **Response generator** (`services/response_generator.py`): LangChain PromptTemplate-based generation with formal and friendly tone modes; low-confidence responses automatically flagged `requires_review: true`
- **Pre-written template responses** for all 7 categories as fallback when API is unavailable
- **Ticket processing pipeline** (`services/ticket_processor.py`): async orchestration of the full ticket lifecycle — receive → classify → generate → persist → status update
- **Background task processing**: `process_ticket_background()` runs outside the HTTP request cycle so `POST /tickets` responds in milliseconds regardless of AI latency

#### REST API
- `POST /tickets` — submit a new support ticket (AI processing enqueued as background task)
- `GET  /tickets` — paginated ticket list with optional `status`, `category`, `date_from`, `date_to` filters
- `GET  /tickets/{id}` — full ticket detail including AI classification and generated response
- `PUT  /tickets/{id}/approve` — approve or provide an edited version of the AI-generated response
- `GET  /analytics/response-time` — real-time metrics: avg AI response time vs manual baseline, time saved per ticket, improvement %, tickets by category and status
- `POST /admin/seed` — populate 20 realistic demo tickets (idempotent)
- `GET  /health` — health check (status, version, environment)

#### Database
- **Tickets table**: id, customer_name, customer_email, subject, message, status, category, confidence_score, created_at, processed_at
- **Responses table**: id, ticket_id (FK), generated_response, is_approved, final_response, response_time_seconds, created_at, approved_at
- **Alembic migrations**: versioned schema (`001_initial_schema`) with full upgrade and downgrade paths
- Async SQLAlchemy 2.0 engine with automatic driver selection (asyncpg for PostgreSQL, aiosqlite for SQLite)

#### Testing
- 43 pytest tests across 3 test files with in-memory SQLite (no external services required)
- `test_intent_classifier.py`: 13 tests — keyword matching, AI response parsing, confidence clamping, async fallback
- `test_response_generator.py`: 8 tests — template coverage, review flag logic, tone preservation
- `test_api.py`: 22 integration tests — all endpoints, error cases, filter logic
- 85%+ coverage enforced via `pytest-cov` in `pyproject.toml`

#### DevOps
- `Dockerfile` — python:3.11-slim base, dependency layer caching, non-root `appuser`, built-in health check
- `docker-compose.yml` — app + postgres:16-alpine with `depends_on: condition: service_healthy`
- `.dockerignore` — excludes dev artifacts, `.env`, docs, and cache from the image
- `Makefile` — shortcuts for `dev`, `test`, `test-cov`, `migrate`, `seed`, `docker-up`, `docker-down`, `clean`
- `.editorconfig` — consistent formatting across editors (4-space indent, LF line endings)
- GitHub Actions CI — runs `pytest` + `flake8` on push/PR to `main`; enforces 85% coverage

#### Documentation
- `README.md` — ASCII architecture diagram, tech stack table, project structure map, local and Docker setup guides, full API reference with sample `curl` requests, migration commands, design decisions, response time improvement metrics
- `CONTRIBUTING.md` — GitHub Flow branching strategy, Conventional Commits guide, PR template, code standards (PEP 8, type hints, docstrings, SQLAlchemy 2.0 patterns)
- `app/tests/README.md` — test run instructions, coverage report guide, fixture reference
- `CHANGELOG.md` — this file

### Configuration
- All secrets and tunable settings via environment variables (see `.env.example`)
- `CONFIDENCE_THRESHOLD` — float controlling when responses are flagged for human review (default `0.75`)
- `MANUAL_RESPONSE_TIME_SECONDS` / `AI_RESPONSE_TIME_SECONDS` — analytics baseline values
- `OPENAI_MODEL`, `OPENAI_TEMPERATURE`, `OPENAI_MAX_TOKENS` — LangChain / OpenAI tuning

---

[1.0.0]: https://github.com/kalavakuntabharathkumar/AI-Powered-Customer-Support-Automation-System/releases/tag/v1.0.0
