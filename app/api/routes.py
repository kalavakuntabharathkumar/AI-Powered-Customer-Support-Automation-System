"""
REST API Endpoints
==================
All HTTP route handlers for the support automation system.

Available endpoints:
  POST   /tickets                     — submit a new support ticket
  GET    /tickets                     — list tickets with optional filters
  GET    /tickets/{id}                — retrieve full ticket detail
  PUT    /tickets/{id}/approve        — approve or edit an AI-generated response
  GET    /analytics/response-time     — response time improvement metrics
  POST   /admin/seed                  — populate demo data (dev/staging only)
  GET    /health                      — health check
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.connection import get_session
from app.models.database import Response, Ticket, TicketCategory, TicketStatus
from app.models.schemas import (
    ApproveRequest,
    HealthResponse,
    ResponseTimeMetrics,
    TicketCreate,
    TicketDetail,
    TicketListItem,
)
from app.services.ticket_processor import process_ticket_background, seed_demo_data

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    tags=["System"],
)
async def health_check() -> HealthResponse:
    """
    Return the current health status of the API.

    Always returns HTTP 200 when the application is running.
    """
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        environment=settings.APP_ENV,
    )


# ---------------------------------------------------------------------------
# Ticket endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/tickets",
    response_model=TicketDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new support ticket",
    tags=["Tickets"],
)
async def create_ticket(
    payload: TicketCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
) -> TicketDetail:
    """
    Accept a new customer support ticket and enqueue it for AI processing.

    The ticket is persisted immediately with status PENDING. AI classification
    and response generation run asynchronously in the background so the caller
    receives a fast response.

    Args:
        payload: Ticket submission data.
        background_tasks: FastAPI background task runner.
        db: Async database session.

    Returns:
        The newly created ticket with status PENDING.
    """
    ticket = Ticket(
        customer_name=payload.customer_name,
        customer_email=payload.customer_email,
        subject=payload.subject,
        message=payload.message,
        status=TicketStatus.PENDING,
    )
    db.add(ticket)
    await db.flush()
    await db.refresh(ticket)

    # Enqueue background processing so the HTTP response is not blocked
    background_tasks.add_task(process_ticket_background, ticket.id)

    logger.info("Created ticket id=%d, enqueued for processing.", ticket.id)
    return TicketDetail.model_validate(ticket)


@router.get(
    "/tickets",
    response_model=List[TicketListItem],
    summary="List all tickets with optional filters",
    tags=["Tickets"],
)
async def list_tickets(
    status: Optional[TicketStatus] = Query(None, description="Filter by ticket status"),
    category: Optional[TicketCategory] = Query(None, description="Filter by category"),
    date_from: Optional[datetime] = Query(None, description="Include tickets created on or after this UTC datetime"),
    date_to: Optional[datetime] = Query(None, description="Include tickets created on or before this UTC datetime"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip for pagination"),
    db: AsyncSession = Depends(get_session),
) -> List[TicketListItem]:
    """
    Return a paginated list of tickets, with optional filtering.

    Filters can be combined freely. Results are ordered by creation time descending.

    Args:
        status: Optional status filter.
        category: Optional category filter.
        date_from: Optional lower bound on created_at.
        date_to: Optional upper bound on created_at.
        limit: Page size (max 200).
        offset: Pagination offset.
        db: Async database session.

    Returns:
        List of TicketListItem summaries.
    """
    query = select(Ticket).order_by(Ticket.created_at.desc())

    if status:
        query = query.where(Ticket.status == status)
    if category:
        query = query.where(Ticket.category == category)
    if date_from:
        query = query.where(Ticket.created_at >= date_from)
    if date_to:
        query = query.where(Ticket.created_at <= date_to)

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    tickets = result.scalars().all()

    return [TicketListItem.model_validate(t) for t in tickets]


@router.get(
    "/tickets/{ticket_id}",
    response_model=TicketDetail,
    summary="Retrieve a ticket with its AI classification and response",
    tags=["Tickets"],
)
async def get_ticket(
    ticket_id: int,
    db: AsyncSession = Depends(get_session),
) -> TicketDetail:
    """
    Return the full detail of a single ticket including AI results.

    Args:
        ticket_id: Primary key of the ticket.
        db: Async database session.

    Returns:
        TicketDetail with embedded response data.

    Raises:
        HTTPException 404: When the ticket does not exist.
    """
    result = await db.execute(
        select(Ticket)
        .options(selectinload(Ticket.response))
        .where(Ticket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()

    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket with id={ticket_id} was not found.",
        )

    return TicketDetail.model_validate(ticket)


@router.put(
    "/tickets/{ticket_id}/approve",
    response_model=TicketDetail,
    summary="Approve or edit an AI-generated response",
    tags=["Tickets"],
)
async def approve_ticket_response(
    ticket_id: int,
    payload: ApproveRequest,
    db: AsyncSession = Depends(get_session),
) -> TicketDetail:
    """
    Mark an AI-generated response as approved, optionally providing an edited version.

    Only tickets in AWAITING_APPROVAL or APPROVED status can be updated.
    On approval the ticket moves to RESOLVED status.

    Args:
        ticket_id: Primary key of the ticket.
        payload: Approval decision and optional edited response.
        db: Async database session.

    Returns:
        Updated TicketDetail.

    Raises:
        HTTPException 404: When the ticket or its response does not exist.
        HTTPException 409: When the ticket is not in an approvable state.
    """
    result = await db.execute(
        select(Ticket)
        .options(selectinload(Ticket.response))
        .where(Ticket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()

    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket with id={ticket_id} was not found.",
        )

    if ticket.response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This ticket has no AI-generated response yet. It may still be processing.",
        )

    if ticket.status not in (TicketStatus.AWAITING_APPROVAL, TicketStatus.APPROVED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ticket is in status '{ticket.status.value}' and cannot be approved at this stage.",
        )

    ticket.response.is_approved = payload.approved
    if payload.edited_response:
        ticket.response.final_response = payload.edited_response
    ticket.response.approved_at = datetime.now(timezone.utc)

    if payload.approved:
        ticket.status = TicketStatus.RESOLVED

    await db.flush()
    await db.refresh(ticket)
    await db.refresh(ticket.response)

    logger.info("Ticket id=%d response approved=%s", ticket_id, payload.approved)
    return TicketDetail.model_validate(ticket)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


@router.get(
    "/analytics/response-time",
    response_model=ResponseTimeMetrics,
    summary="Response time improvement analytics",
    tags=["Analytics"],
)
async def get_response_time_analytics(
    db: AsyncSession = Depends(get_session),
) -> ResponseTimeMetrics:
    """
    Return metrics comparing manual vs AI-assisted response times.

    Demonstrates the automation value: shows average AI processing time
    against the baseline manual handling time configured in settings.

    Args:
        db: Async database session.

    Returns:
        ResponseTimeMetrics with per-category breakdowns and improvement %.
    """
    # Total and processed ticket counts
    total_result = await db.execute(select(func.count()).select_from(Ticket))
    total_tickets: int = total_result.scalar() or 0

    processed_result = await db.execute(
        select(func.count()).select_from(Ticket).where(
            Ticket.status.in_([TicketStatus.APPROVED, TicketStatus.RESOLVED, TicketStatus.AWAITING_APPROVAL])
        )
    )
    processed_tickets: int = processed_result.scalar() or 0

    # Approved response count
    approved_result = await db.execute(
        select(func.count()).select_from(Response).where(Response.is_approved == True)  # noqa: E712
    )
    approved_responses: int = approved_result.scalar() or 0

    # Average AI response time
    avg_time_result = await db.execute(
        select(func.avg(Response.response_time_seconds)).where(
            Response.response_time_seconds.is_not(None)
        )
    )
    avg_ai_time: Optional[float] = avg_time_result.scalar()

    # Tickets by category
    category_result = await db.execute(
        select(Ticket.category, func.count().label("cnt"))
        .where(Ticket.category.is_not(None))
        .group_by(Ticket.category)
    )
    tickets_by_category = {row.category.value: row.cnt for row in category_result}

    # Tickets by status
    status_result = await db.execute(
        select(Ticket.status, func.count().label("cnt")).group_by(Ticket.status)
    )
    tickets_by_status = {row.status.value: row.cnt for row in status_result}

    # Compute savings
    manual_time = float(settings.MANUAL_RESPONSE_TIME_SECONDS)
    time_saved: Optional[float] = None
    improvement_pct: Optional[float] = None

    if avg_ai_time is not None:
        time_saved = max(0.0, manual_time - avg_ai_time)
        improvement_pct = round((time_saved / manual_time) * 100, 1) if manual_time > 0 else None

    return ResponseTimeMetrics(
        total_tickets=total_tickets,
        processed_tickets=processed_tickets,
        approved_responses=approved_responses,
        avg_ai_response_time_seconds=round(avg_ai_time, 2) if avg_ai_time else None,
        avg_manual_response_time_seconds=manual_time,
        time_saved_per_ticket_seconds=round(time_saved, 2) if time_saved is not None else None,
        time_saved_per_ticket_minutes=round(time_saved / 60, 1) if time_saved is not None else None,
        improvement_percentage=improvement_pct,
        tickets_by_category=tickets_by_category,
        tickets_by_status=tickets_by_status,
    )


# ---------------------------------------------------------------------------
# Admin / Demo utilities
# ---------------------------------------------------------------------------


@router.post(
    "/admin/seed",
    summary="Seed demo data (development only)",
    tags=["Admin"],
    status_code=status.HTTP_200_OK,
)
async def seed_data() -> dict:
    """
    Populate the database with 20 sample tickets for demonstration purposes.

    This endpoint is intended for development and staging environments only.
    Skips seeding if sufficient data already exists.

    Returns:
        Dictionary with the count of inserted tickets.
    """
    count = await seed_demo_data()
    return {"inserted": count, "message": f"Inserted {count} demo tickets."}
