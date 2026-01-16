.PHONY: help dev test test-cov lint format install migrate seed docker-up docker-down docker-logs clean

# Display available targets
help:
	@echo ""
	@echo "AI Customer Support Automation System — Developer Commands"
	@echo "==========================================================="
	@echo ""
	@echo "  make install       Install Python dependencies"
	@echo "  make dev           Start the FastAPI dev server (hot-reload)"
	@echo "  make test          Run the test suite"
	@echo "  make test-cov      Run tests with HTML coverage report"
	@echo "  make lint          Run flake8 linter"
	@echo "  make format        Format code with black + isort"
	@echo "  make migrate       Apply all pending Alembic migrations"
	@echo "  make seed          Populate demo data via API"
	@echo "  make docker-up     Build and start Docker services"
	@echo "  make docker-down   Stop and remove Docker containers"
	@echo "  make docker-logs   Tail Docker service logs"
	@echo "  make clean         Remove cache files and coverage artifacts"
	@echo ""

# Install dependencies
install:
	pip install -r requirements.txt

# Start development server
dev:
	uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Run tests
test:
	pytest -v

# Run tests with full HTML coverage report
test-cov:
	pytest --cov=app --cov-report=term-missing --cov-report=html
	@echo "\nHTML coverage report: htmlcov/index.html"

# Lint with flake8
lint:
	flake8 app/ main.py --max-line-length=100 --exclude=app/tests/

# Format with black and isort
format:
	black app/ main.py --line-length=100
	isort app/ main.py --profile=black

# Apply Alembic migrations
migrate:
	alembic upgrade head

# Generate a new migration (usage: make migration MSG="describe change")
migration:
	alembic revision --autogenerate -m "$(MSG)"

# Seed demo data
seed:
	curl -s -X POST http://localhost:8000/admin/seed | python3 -m json.tool

# Docker commands
docker-up:
	docker-compose up --build -d
	@echo "\nServices started. API: http://localhost:8000 | Docs: http://localhost:8000/docs"

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f app

# Clean up cache and build artifacts
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache htmlcov .coverage coverage.xml
	rm -f support_dev.db
	@echo "Cleaned."
