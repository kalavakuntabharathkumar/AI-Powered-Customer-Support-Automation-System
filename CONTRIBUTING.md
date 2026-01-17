# Contributing Guidelines

Thank you for your interest in contributing to the AI-Powered Customer Support Automation System. This document outlines our development workflow, branching strategy, and code standards.

---

## Getting Started

1. Fork the repository on GitHub.
2. Clone your fork locally:
   ```bash
   git clone https://github.com/<your-username>/AI-Powered-Customer-Support-Automation-System.git
   cd AI-Powered-Customer-Support-Automation-System
   ```
3. Add the upstream remote:
   ```bash
   git remote add upstream https://github.com/kalavakuntabharathkumar/AI-Powered-Customer-Support-Automation-System.git
   ```
4. Create a virtual environment and install dependencies:
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
5. Copy `.env.example` to `.env` and fill in your values.

---

## Branching Strategy

We follow **GitHub Flow** — a lightweight, branch-based workflow.

```
main
 ├── feature/add-slack-integration
 ├── feature/batch-ticket-processing
 ├── fix/classification-confidence-edge-case
 └── chore/update-langchain-dependency
```

### Branch naming conventions

| Type | Pattern | Example |
|---|---|---|
| New feature | `feature/<short-description>` | `feature/email-notification-service` |
| Bug fix | `fix/<short-description>` | `fix/ticket-status-transition-bug` |
| Documentation | `docs/<short-description>` | `docs/api-authentication-guide` |
| Dependency / tooling | `chore/<short-description>` | `chore/upgrade-fastapi-0.110` |
| Hotfix (urgent prod fix) | `hotfix/<short-description>` | `hotfix/null-confidence-crash` |

### Rules

- **Never commit directly to `main`**. All changes go through pull requests.
- Keep branches short-lived. Aim to merge within 2-3 days of opening.
- Rebase on `main` before opening a PR to keep history linear:
  ```bash
  git fetch upstream
  git rebase upstream/main
  ```

---

## Commit Message Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short summary in imperative mood>

[optional body — explains the why, not the what]

[optional footer — issue references, breaking change notices]
```

### Types

| Type | When to use |
|---|---|
| `feat` | A new feature or endpoint |
| `fix` | A bug fix |
| `docs` | Documentation changes only |
| `refactor` | Code restructure without behaviour change |
| `test` | Adding or updating tests |
| `chore` | Dependency updates, tooling, CI config |
| `perf` | Performance improvement |

### Examples

```
feat(classifier): add confidence score to classification result

fix(api): return 409 instead of 500 when ticket is not in approvable state

test(response-generator): add fallback template coverage for all categories

chore(deps): upgrade langchain to 0.1.5
```

---

## Pull Request Process

1. **Open a draft PR early** — this signals work in progress and invites early feedback.
2. **Fill in the PR template** — describe what changed, why, and how to test it.
3. **Ensure all checks pass**:
   - `pytest` — all tests green
   - Coverage ≥ 85% (`pytest --cov=app --cov-fail-under=85`)
   - No linting errors (if flake8/ruff is configured)
4. **Request a review** — at least one approval is required before merging.
5. **Squash or rebase merge** — keep `main` history clean and linear.

### PR Template

When opening a pull request, include:

```markdown
## Summary
<!-- One paragraph describing the change and the motivation behind it. -->

## Changes
- [ ] Item 1
- [ ] Item 2

## Testing
<!-- How did you verify the change works? Which test cases cover it? -->

## Screenshots / Logs (if applicable)

## Related Issues
<!-- Closes #<issue-number> -->
```

---

## Code Standards

### Python style

- Follow [PEP 8](https://pep8.org/) style guidelines.
- Use type hints on all public functions and class attributes.
- Write docstrings for all public modules, classes, and functions (Google style).
- Maximum line length: **100 characters**.

### FastAPI conventions

- Use `async def` for all route handlers and service functions.
- Return Pydantic models directly — never raw dicts from endpoints.
- Use `Depends()` for all database sessions, settings, and shared services.
- Prefix route tags consistently: `Tickets`, `Analytics`, `System`, `Admin`.

### SQLAlchemy conventions

- Use SQLAlchemy 2.0 `Mapped[]` typed columns in ORM models.
- Prefer `select()` + `scalars()` over deprecated `Query` API.
- Never use synchronous session in async code.

### Testing conventions

- Every new feature must include unit tests.
- API tests use an in-memory SQLite database — no external services required.
- Use `monkeypatch` to isolate external API calls (OpenAI, LangChain).
- Aim for 85% or higher code coverage.

---

## Environment Variables

Never hardcode secrets. All configurable values must be added to:
1. `.env.example` (with a placeholder value and comment)
2. `app/core/config.py` as a `Settings` field with a safe default

---

## Running the Full Test Suite Before Submitting

```bash
# Activate your virtual environment first
source venv/bin/activate

# Run all tests with coverage report
pytest

# If coverage drops below 85%, add tests before opening the PR
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

---

## Reporting Issues

Please open a GitHub Issue with:
- A clear title and description
- Steps to reproduce (for bugs)
- Expected vs actual behaviour
- Environment details (Python version, OS)

---

Thank you for helping make this project better!
