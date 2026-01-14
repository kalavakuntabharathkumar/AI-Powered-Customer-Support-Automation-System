"""
Ticket Processing Automation Module
=====================================
Orchestrates the full ticket lifecycle:
  receive → classify intent → generate response → persist to database

Also provides seed data generation for demo and analytics population.
"""

import asyncio
import logging
import random
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.connection import AsyncSessionLocal
from app.models.database import Response, Ticket, TicketCategory, TicketStatus
from app.services.intent_classifier import classify_intent
from app.services.response_generator import generate_response

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core processing pipeline
# ---------------------------------------------------------------------------


async def process_ticket(ticket: Ticket, db: AsyncSession) -> Ticket:
    """
    Run the full AI processing pipeline for a single ticket.

    Steps:
      1. Mark ticket as PROCESSING
      2. Classify intent with AI (or fallback)
      3. Generate contextual response
      4. Persist results and mark as AWAITING_APPROVAL or APPROVED

    Args:
        ticket: The ORM Ticket instance (must already be persisted).
        db: Active async database session.

    Returns:
        The updated Ticket instance.
    """
    processing_start = datetime.now(timezone.utc)

    try:
        # Step 1 — Mark as processing
        ticket.status = TicketStatus.PROCESSING
        await db.flush()
        logger.info("Processing ticket id=%d subject=%r", ticket.id, ticket.subject)

        # Step 2 — Classify intent
        classification = await classify_intent(ticket.subject, ticket.message)
        logger.info(
            "Ticket id=%d classified as %s (confidence=%.2f, fallback=%s)",
            ticket.id,
            classification.category,
            classification.confidence,
            classification.used_fallback,
        )

        # Step 3 — Generate response
        generated = await generate_response(
            customer_name=ticket.customer_name,
            subject=ticket.subject,
            message=ticket.message,
            category=classification.category,
            confidence=classification.confidence,
            tone="friendly",
        )

        # Step 4 — Persist results
        processing_end = datetime.now(timezone.utc)
        response_time = (processing_end - processing_start).total_seconds()

        ticket.category = classification.category
        ticket.confidence_score = classification.confidence
        ticket.processed_at = processing_end
        ticket.status = (
            TicketStatus.AWAITING_APPROVAL
            if generated.requires_review
            else TicketStatus.APPROVED
        )

        db_response = Response(
            ticket_id=ticket.id,
            generated_response=generated.content,
            is_approved=not generated.requires_review,
            response_time_seconds=response_time,
        )
        db.add(db_response)
        await db.flush()

        logger.info(
            "Ticket id=%d processed in %.2fs → status=%s",
            ticket.id,
            response_time,
            ticket.status,
        )

    except Exception as exc:
        logger.error("Failed to process ticket id=%d: %s", ticket.id, exc)
        ticket.status = TicketStatus.FAILED

    return ticket


async def process_ticket_background(ticket_id: int) -> None:
    """
    Background task entry point for processing a single ticket.

    Opens a fresh database session to safely run outside the request lifecycle.

    Args:
        ticket_id: Primary key of the ticket to process.
    """
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select

        result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = result.scalar_one_or_none()

        if ticket is None:
            logger.error("Background task: ticket id=%d not found.", ticket_id)
            return

        await process_ticket(ticket, db)
        await db.commit()


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

_SEED_TICKETS: list[dict] = [
    {"customer_name": "Alice Johnson", "customer_email": "alice.johnson@email.com", "subject": "Invoice amount is incorrect", "message": "Hi, I was charged $149 this month but my plan is $99/month. There seems to be an error on my latest invoice. Please investigate and refund the difference as soon as possible."},
    {"customer_name": "Bob Martinez", "customer_email": "bob.m@company.com", "subject": "Application crashes on login", "message": "Every time I try to log in on the mobile app, it crashes immediately. I've reinstalled it twice and the issue persists. Running iOS 17.2 on iPhone 15. This is critical for my work."},
    {"customer_name": "Carol White", "customer_email": "carol.w@startup.io", "subject": "Cannot reset my password", "message": "The password reset email never arrives. I've checked spam and waited 30 minutes. My email is carol.w@startup.io. I'm completely locked out of my account."},
    {"customer_name": "David Chen", "customer_email": "david.chen@enterprise.com", "subject": "Feature request: bulk export to CSV", "message": "It would be incredibly useful to be able to export all tickets to CSV at once instead of one by one. Our team reviews reports weekly and this would save hours each month."},
    {"customer_name": "Emma Thompson", "customer_email": "emma.t@email.com", "subject": "How do I integrate with Slack?", "message": "I saw on your website that Slack integration is supported, but I can't find the documentation. Could you point me to the setup guide? We want to receive ticket notifications in our #support channel."},
    {"customer_name": "Frank Rivera", "customer_email": "frank.r@corp.com", "subject": "Absolutely terrible service!", "message": "I've been waiting 5 days for a response to my billing issue and nobody has gotten back to me. This is completely unacceptable. I'm a premium subscriber paying $299/month and I deserve better support."},
    {"customer_name": "Grace Lee", "customer_email": "grace.l@tech.com", "subject": "API timeout errors on high traffic", "message": "We're seeing HTTP 504 timeout errors on the /api/v2/tickets endpoint when we have more than 100 concurrent requests. Our load tests confirm it. Please look into the rate limiting configuration."},
    {"customer_name": "Henry Wilson", "customer_email": "henry.w@email.com", "subject": "Subscription upgrade question", "message": "I'm currently on the Starter plan and want to upgrade to Pro mid-billing cycle. How will I be charged? Will I receive a prorated invoice?"},
    {"customer_name": "Isabel Garcia", "customer_email": "isabel.g@agency.com", "subject": "Two-factor authentication not working", "message": "Since this morning, my 2FA codes are being rejected even though I haven't changed anything. I'm using Google Authenticator. Is there a server-side issue?"},
    {"customer_name": "James Brown", "customer_email": "james.b@company.com", "subject": "Dashboard widgets not loading", "message": "The analytics widgets on our team dashboard show a spinner indefinitely. The console shows: 'Failed to fetch: NetworkError'. This started after your maintenance window last night."},
    {"customer_name": "Karen Davis", "customer_email": "karen.d@firm.com", "subject": "Request: dark mode support", "message": "Would love to see a dark mode option in the settings. Many of us work late and the bright interface is hard on the eyes. This is a commonly requested feature in the community forum too."},
    {"customer_name": "Liam O'Connor", "customer_email": "liam.oc@email.com", "subject": "What is the data retention policy?", "message": "Before we migrate our customer data to your platform, we need to understand how long you retain data and whether we can request deletion. Is there a DPA (Data Processing Agreement) available?"},
    {"customer_name": "Mia Patel", "customer_email": "mia.p@startup.com", "subject": "Charged twice for the same month", "message": "My credit card statement shows two identical charges of $79 on the 1st and 3rd of this month. I only have one account. Please refund one of these immediately."},
    {"customer_name": "Noah Williams", "customer_email": "noah.w@tech.io", "subject": "Webhook delivery failures", "message": "Our webhook endpoint is receiving duplicate events and sometimes no events at all. The event log shows them as 'delivered' but our server logs don't show any incoming requests. Retry policy seems broken."},
    {"customer_name": "Olivia Miller", "customer_email": "olivia.m@corp.com", "subject": "How to add team members?", "message": "I'm the account admin and want to invite 5 new team members. I can see the 'Users' section but the 'Invite' button is greyed out. What do I need to do to enable it?"},
    {"customer_name": "Paul Anderson", "customer_email": "paul.a@email.com", "subject": "Extremely disappointed with product quality", "message": "The platform has been down three times this week. Each time we lose access for 1-2 hours during business hours. Our team's productivity is severely impacted. We are considering switching providers."},
    {"customer_name": "Quinn Taylor", "customer_email": "quinn.t@design.com", "subject": "Export to PDF is corrupted", "message": "When I export reports to PDF, the charts are missing and some tables are cut off at the page boundary. The HTML version looks fine. This affects every PDF export regardless of browser."},
    {"customer_name": "Rachel Kim", "customer_email": "rachel.k@company.com", "subject": "Annual plan discount inquiry", "message": "I've been a monthly subscriber for 18 months. Do you offer a retroactive discount if I switch to annual billing? I saw a 20% discount advertised for annual plans."},
    {"customer_name": "Samuel Jackson", "customer_email": "samuel.j@enterprise.com", "subject": "SSO configuration help needed", "message": "We're trying to configure SAML SSO with Okta as our IdP but keep getting 'Invalid assertion' errors. Our IT team has followed your documentation but the entity ID doesn't match. Can a technical specialist assist?"},
    {"customer_name": "Tina Foster", "customer_email": "tina.f@email.com", "subject": "Missing notifications for critical alerts", "message": "We've configured email notifications for P1 tickets but haven't received any alerts in the past week despite 3 P1 incidents being raised. Notification settings show everything is enabled. Something is broken."},
]


async def seed_demo_data() -> int:
    """
    Populate the database with sample tickets for demonstration purposes.

    Generates 20 realistic support tickets with varied categories and statuses,
    including pre-computed AI processing results to showcase analytics.

    Returns:
        Number of tickets inserted.
    """
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select, func

        # Avoid re-seeding if data already exists
        count_result = await db.execute(select(func.count()).select_from(Ticket))
        existing = count_result.scalar()
        if existing and existing >= 10:
            logger.info("Seed data already present (%d tickets) — skipping.", existing)
            return 0

        categories = list(TicketCategory)
        statuses = [TicketStatus.APPROVED, TicketStatus.AWAITING_APPROVAL, TicketStatus.RESOLVED]

        inserted = 0
        for i, seed in enumerate(_SEED_TICKETS):
            category = categories[i % len(categories)]
            status = statuses[i % len(statuses)]
            confidence = round(random.uniform(0.60, 0.98), 2)
            response_time = round(random.uniform(1.5, 8.0), 2)

            ticket = Ticket(
                customer_name=seed["customer_name"],
                customer_email=seed["customer_email"],
                subject=seed["subject"],
                message=seed["message"],
                status=status,
                category=category,
                confidence_score=confidence,
                processed_at=datetime.now(timezone.utc),
            )
            db.add(ticket)
            await db.flush()

            response = Response(
                ticket_id=ticket.id,
                generated_response=(
                    f"Dear {seed['customer_name'].split()[0]}, thank you for reaching out. "
                    f"We've received your {category.value.replace('_', ' ')} request and our team "
                    "is already looking into it. We'll get back to you within 24 hours with a resolution."
                ),
                is_approved=(status == TicketStatus.APPROVED or status == TicketStatus.RESOLVED),
                response_time_seconds=response_time,
            )
            db.add(response)
            inserted += 1

        await db.commit()
        logger.info("Seeded %d demo tickets.", inserted)
        return inserted
