"""
SQLAlchemy ORM models for the support automation system.

Tables:
  - tickets   — incoming customer support tickets
  - responses — AI-generated (and optionally human-edited) responses
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.connection import Base


class TicketStatus(str, enum.Enum):
    """Lifecycle states of a support ticket."""

    PENDING = "pending"
    PROCESSING = "processing"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    RESOLVED = "resolved"
    FAILED = "failed"


class TicketCategory(str, enum.Enum):
    """Intent categories assigned by the classifier."""

    BILLING = "billing"
    TECHNICAL = "technical"
    ACCOUNT = "account"
    GENERAL_INQUIRY = "general_inquiry"
    COMPLAINT = "complaint"
    FEATURE_REQUEST = "feature_request"
    UNKNOWN = "unknown"


class Ticket(Base):
    """
    Represents a customer support ticket.

    Stores the original request, AI classification results, and processing metadata.
    """

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus),
        default=TicketStatus.PENDING,
        nullable=False,
        index=True,
    )
    category: Mapped[TicketCategory | None] = mapped_column(
        Enum(TicketCategory),
        nullable=True,
        index=True,
    )
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # One-to-one relationship with the generated response
    response: Mapped["Response | None"] = relationship(
        "Response", back_populates="ticket", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Ticket id={self.id} subject={self.subject!r} status={self.status}>"


class Response(Base):
    """
    Stores the AI-generated response for a ticket.

    Tracks both the raw generated output and any human-edited final version.
    """

    __tablename__ = "responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticket_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    generated_response: Mapped[str] = mapped_column(Text, nullable=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    final_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="response")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Response id={self.id} ticket_id={self.ticket_id} approved={self.is_approved}>"
