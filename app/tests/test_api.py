"""
Integration tests for the REST API endpoints.

Tests cover:
  - Health check endpoint
  - Ticket creation (POST /tickets)
  - Ticket retrieval (GET /tickets/{id})
  - Ticket listing with filters (GET /tickets)
  - Response approval (PUT /tickets/{id}/approve)
  - Analytics endpoint (GET /analytics/response-time)
  - Error cases (404, 409)
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.connection import Base, get_session
from app.models.database import Response, Ticket, TicketCategory, TicketStatus
from main import app

# ---------------------------------------------------------------------------
# Test database setup (in-memory SQLite)
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)


async def override_get_session():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


app.dependency_overrides[get_session] = override_get_session


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Create all tables before each test and drop them after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    """Async HTTP client wired to the FastAPI test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def sample_ticket():
    """Persist a pre-processed sample ticket for use in multiple tests."""
    async with TestSessionLocal() as db:
        ticket = Ticket(
            customer_name="Test User",
            customer_email="test@example.com",
            subject="Test ticket subject",
            message="This is a detailed test ticket message for testing purposes.",
            status=TicketStatus.AWAITING_APPROVAL,
            category=TicketCategory.TECHNICAL,
            confidence_score=0.85,
        )
        db.add(ticket)
        await db.flush()

        response = Response(
            ticket_id=ticket.id,
            generated_response="Thank you for your report. Our team will investigate this technical issue.",
            is_approved=False,
            response_time_seconds=2.34,
        )
        db.add(response)
        await db.commit()
        await db.refresh(ticket)
        return ticket.id


# ---------------------------------------------------------------------------
# Health check tests
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, client):
        response = await client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_returns_healthy_status(self, client):
        response = await client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_returns_version(self, client):
        response = await client.get("/health")
        data = response.json()
        assert "version" in data
        assert "environment" in data


# ---------------------------------------------------------------------------
# Ticket creation tests
# ---------------------------------------------------------------------------


class TestCreateTicket:
    @pytest.mark.asyncio
    async def test_create_ticket_returns_201(self, client):
        payload = {
            "customer_name": "Jane Doe",
            "customer_email": "jane@example.com",
            "subject": "Login issue",
            "message": "I cannot login to my account after the latest update.",
        }
        response = await client.post("/tickets", json=payload)
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_ticket_returns_ticket_data(self, client):
        payload = {
            "customer_name": "John Smith",
            "subject": "Billing query",
            "message": "I was charged incorrectly on my latest invoice this month.",
        }
        response = await client.post("/tickets", json=payload)
        data = response.json()
        assert data["customer_name"] == "John Smith"
        assert data["subject"] == "Billing query"
        assert "id" in data
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_ticket_missing_required_fields(self, client):
        payload = {"customer_name": "Alice"}
        response = await client.post("/tickets", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_ticket_message_too_short(self, client):
        payload = {
            "customer_name": "Bob",
            "subject": "Help",
            "message": "Hi",  # Less than 10 characters
        }
        response = await client.post("/tickets", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_ticket_without_email(self, client):
        payload = {
            "customer_name": "Carol",
            "subject": "Question about features",
            "message": "I have a question about the available features in the plan.",
        }
        response = await client.post("/tickets", json=payload)
        assert response.status_code == 201
        assert response.json()["customer_email"] is None


# ---------------------------------------------------------------------------
# Ticket retrieval tests
# ---------------------------------------------------------------------------


class TestGetTicket:
    @pytest.mark.asyncio
    async def test_get_existing_ticket(self, client, sample_ticket):
        response = await client.get(f"/tickets/{sample_ticket}")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_ticket_contains_correct_data(self, client, sample_ticket):
        response = await client.get(f"/tickets/{sample_ticket}")
        data = response.json()
        assert data["id"] == sample_ticket
        assert data["customer_name"] == "Test User"
        assert data["category"] == "technical"

    @pytest.mark.asyncio
    async def test_get_ticket_includes_response(self, client, sample_ticket):
        response = await client.get(f"/tickets/{sample_ticket}")
        data = response.json()
        assert "response" in data
        assert data["response"] is not None
        assert "generated_response" in data["response"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_ticket_returns_404(self, client):
        response = await client.get("/tickets/99999")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Ticket listing tests
# ---------------------------------------------------------------------------


class TestListTickets:
    @pytest.mark.asyncio
    async def test_list_tickets_returns_200(self, client, sample_ticket):
        response = await client.get("/tickets")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_tickets_returns_array(self, client, sample_ticket):
        response = await client.get("/tickets")
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_list_tickets_filter_by_status(self, client, sample_ticket):
        response = await client.get("/tickets?status=awaiting_approval")
        data = response.json()
        assert all(t["status"] == "awaiting_approval" for t in data)

    @pytest.mark.asyncio
    async def test_list_tickets_filter_by_category(self, client, sample_ticket):
        response = await client.get("/tickets?category=technical")
        data = response.json()
        assert all(t["category"] == "technical" for t in data)

    @pytest.mark.asyncio
    async def test_list_tickets_limit_and_offset(self, client, sample_ticket):
        response = await client.get("/tickets?limit=1&offset=0")
        data = response.json()
        assert len(data) <= 1

    @pytest.mark.asyncio
    async def test_list_tickets_empty_database(self, client):
        response = await client.get("/tickets")
        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# Approval endpoint tests
# ---------------------------------------------------------------------------


class TestApproveTicket:
    @pytest.mark.asyncio
    async def test_approve_ticket_returns_200(self, client, sample_ticket):
        response = await client.put(
            f"/tickets/{sample_ticket}/approve",
            json={"approved": True},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_approve_ticket_changes_status_to_resolved(self, client, sample_ticket):
        await client.put(f"/tickets/{sample_ticket}/approve", json={"approved": True})
        detail = await client.get(f"/tickets/{sample_ticket}")
        assert detail.json()["status"] == "resolved"

    @pytest.mark.asyncio
    async def test_approve_with_edited_response(self, client, sample_ticket):
        payload = {
            "approved": True,
            "edited_response": "This is the human-edited final response for the customer.",
        }
        response = await client.put(f"/tickets/{sample_ticket}/approve", json=payload)
        data = response.json()
        assert data["response"]["final_response"] == payload["edited_response"]

    @pytest.mark.asyncio
    async def test_approve_nonexistent_ticket_returns_404(self, client):
        response = await client.put("/tickets/99999/approve", json={"approved": True})
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Analytics endpoint tests
# ---------------------------------------------------------------------------


class TestAnalyticsEndpoint:
    @pytest.mark.asyncio
    async def test_analytics_returns_200(self, client):
        response = await client.get("/analytics/response-time")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_analytics_contains_required_fields(self, client):
        response = await client.get("/analytics/response-time")
        data = response.json()
        required_fields = [
            "total_tickets",
            "processed_tickets",
            "approved_responses",
            "avg_manual_response_time_seconds",
            "tickets_by_category",
            "tickets_by_status",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_analytics_ticket_count_increases_after_creation(self, client):
        before = (await client.get("/analytics/response-time")).json()["total_tickets"]
        await client.post("/tickets", json={
            "customer_name": "New User",
            "subject": "New ticket",
            "message": "This is a brand new test ticket for analytics testing.",
        })
        after = (await client.get("/analytics/response-time")).json()["total_tickets"]
        assert after == before + 1
