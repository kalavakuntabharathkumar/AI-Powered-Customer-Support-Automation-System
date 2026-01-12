"""
Pydantic v2 schemas for request / response validation and serialisation.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.database import TicketCategory, TicketStatus


# ---------------------------------------------------------------------------
# Ticket schemas
# ---------------------------------------------------------------------------


class TicketCreate(BaseModel):
    """Payload required to submit a new support ticket."""

    customer_name: str = Field(..., min_length=1, max_length=255, description="Full name of the customer")
    customer_email: Optional[str] = Field(None, description="Customer email address")
    subject: str = Field(..., min_length=1, max_length=500, description="Brief summary of the issue")
    message: str = Field(..., min_length=10, description="Full description of the support request")

    @field_validator("customer_name", "subject", "message", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Remove leading/trailing whitespace from string fields."""
        return v.strip()


class ResponseSummary(BaseModel):
    """Condensed response data embedded in ticket detail responses."""

    id: int
    generated_response: str
    is_approved: bool
    final_response: Optional[str]
    response_time_seconds: Optional[float]
    created_at: datetime
    approved_at: Optional[datetime]

    model_config = {"from_attributes": True}


class TicketDetail(BaseModel):
    """Full ticket detail including AI classification and generated response."""

    id: int
    customer_name: str
    customer_email: Optional[str]
    subject: str
    message: str
    status: TicketStatus
    category: Optional[TicketCategory]
    confidence_score: Optional[float]
    created_at: datetime
    processed_at: Optional[datetime]
    response: Optional[ResponseSummary]

    model_config = {"from_attributes": True}


class TicketListItem(BaseModel):
    """Lightweight ticket representation used in list views."""

    id: int
    customer_name: str
    subject: str
    status: TicketStatus
    category: Optional[TicketCategory]
    confidence_score: Optional[float]
    created_at: datetime
    processed_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Response / approval schemas
# ---------------------------------------------------------------------------


class ApproveRequest(BaseModel):
    """Payload for approving or editing an AI-generated response."""

    approved: bool = Field(..., description="Set to true to approve, false to reject")
    edited_response: Optional[str] = Field(
        None,
        description="Optional human-edited version of the generated response",
    )


# ---------------------------------------------------------------------------
# Analytics schemas
# ---------------------------------------------------------------------------


class ResponseTimeMetrics(BaseModel):
    """Analytics payload comparing manual vs AI-assisted response times."""

    total_tickets: int
    processed_tickets: int
    approved_responses: int
    avg_ai_response_time_seconds: Optional[float]
    avg_manual_response_time_seconds: float
    time_saved_per_ticket_seconds: Optional[float]
    time_saved_per_ticket_minutes: Optional[float]
    improvement_percentage: Optional[float]
    tickets_by_category: dict[str, int]
    tickets_by_status: dict[str, int]


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Health check response payload."""

    status: str
    version: str
    environment: str
