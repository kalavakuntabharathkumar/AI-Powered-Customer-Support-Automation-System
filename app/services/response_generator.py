"""
Automated Response Generator Module
=====================================
Generates contextual, tone-aware responses for classified support tickets
using LangChain prompt templates and OpenAI.

Features:
  - Formal and friendly tone options
  - Low-confidence response flagging for human review
  - Fallback template responses when the API is unavailable
"""

import logging
from dataclasses import dataclass
from typing import Literal

from app.core.config import settings
from app.models.database import TicketCategory

logger = logging.getLogger(__name__)

ToneType = Literal["formal", "friendly"]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class GeneratedResponse:
    """
    Result produced by the response generator.

    Attributes:
        content: The generated response text.
        requires_review: True when confidence is below the threshold.
        tone: Tone used to generate this response.
        used_fallback: True when a template response was used.
    """

    content: str
    requires_review: bool
    tone: ToneType
    used_fallback: bool = False


# ---------------------------------------------------------------------------
# Fallback template responses
# ---------------------------------------------------------------------------

_FALLBACK_TEMPLATES: dict[TicketCategory, str] = {
    TicketCategory.BILLING: (
        "Thank you for reaching out regarding your billing query. "
        "Our billing team will review your account and get back to you within 1 business day. "
        "If you have your invoice number available, please reply with it so we can expedite your case."
    ),
    TicketCategory.TECHNICAL: (
        "Thank you for reporting this technical issue. "
        "Our engineering team has been notified and will investigate the problem. "
        "In the meantime, please try clearing your browser cache or restarting the application. "
        "We'll provide an update within 4 hours."
    ),
    TicketCategory.ACCOUNT: (
        "Thank you for contacting us about your account. "
        "For security purposes, we'll need to verify your identity before making any changes. "
        "Please expect an email within 30 minutes with next steps."
    ),
    TicketCategory.GENERAL_INQUIRY: (
        "Thank you for your question. "
        "Our support team will review your inquiry and respond with a detailed answer within 24 hours. "
        "In the meantime, you may find helpful information in our knowledge base at docs.example.com."
    ),
    TicketCategory.COMPLAINT: (
        "Thank you for bringing this to our attention. "
        "We sincerely apologise for the experience you've had. "
        "A senior support representative will personally reach out to you within 2 hours to resolve this."
    ),
    TicketCategory.FEATURE_REQUEST: (
        "Thank you for your suggestion — we genuinely appreciate customer feedback. "
        "Your request has been logged and forwarded to our product team for consideration. "
        "We'll notify you if this feature makes it into our roadmap."
    ),
    TicketCategory.UNKNOWN: (
        "Thank you for contacting our support team. "
        "A representative will review your message and get back to you as soon as possible."
    ),
}


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_FORMAL_PROMPT = """You are a professional customer support specialist. Write a formal, polished response to the following support ticket.

Guidelines:
- Use formal language and avoid contractions
- Address the customer by name
- Acknowledge the issue clearly
- Provide a concrete next step or resolution timeline
- Close professionally
- Keep the response under 200 words

Customer name: {customer_name}
Issue category: {category}
Subject: {subject}
Message: {message}

Write only the response body (no subject line or metadata):"""


_FRIENDLY_PROMPT = """You are a friendly and empathetic customer support specialist. Write a warm, conversational response to the following support ticket.

Guidelines:
- Use a friendly, approachable tone
- Address the customer by their first name
- Show genuine empathy where appropriate
- Be clear and helpful
- Keep the response under 200 words

Customer name: {customer_name}
Issue category: {category}
Subject: {subject}
Message: {message}

Write only the response body (no subject line or metadata):"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def generate_response(
    customer_name: str,
    subject: str,
    message: str,
    category: TicketCategory,
    confidence: float,
    tone: ToneType = "friendly",
) -> GeneratedResponse:
    """
    Generate a contextual response for a classified support ticket.

    Attempts AI generation first; falls back to a pre-written template on any error.

    Args:
        customer_name: Name of the customer (used for personalisation).
        subject: Ticket subject line.
        message: Full ticket message body.
        category: Classified intent category.
        confidence: Classification confidence score.
        tone: Response tone — 'formal' or 'friendly'.

    Returns:
        GeneratedResponse with content and review flag.
    """
    requires_review = confidence < settings.CONFIDENCE_THRESHOLD

    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set — using template response.")
        return GeneratedResponse(
            content=_FALLBACK_TEMPLATES.get(category, _FALLBACK_TEMPLATES[TicketCategory.UNKNOWN]),
            requires_review=True,
            tone=tone,
            used_fallback=True,
        )

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import PromptTemplate
        from langchain_core.output_parsers import StrOutputParser

        llm = ChatOpenAI(
            model=settings.OPENAI_MODEL,
            temperature=settings.OPENAI_TEMPERATURE,
            max_tokens=settings.OPENAI_MAX_TOKENS,
            api_key=settings.OPENAI_API_KEY,
        )

        template_text = _FORMAL_PROMPT if tone == "formal" else _FRIENDLY_PROMPT
        prompt = PromptTemplate.from_template(template_text)
        chain = prompt | llm | StrOutputParser()

        content: str = await chain.ainvoke(
            {
                "customer_name": customer_name,
                "category": category.value,
                "subject": subject,
                "message": message,
            }
        )

        logger.info(
            "Response generated: tone=%s requires_review=%s", tone, requires_review
        )
        return GeneratedResponse(
            content=content.strip(),
            requires_review=requires_review,
            tone=tone,
            used_fallback=False,
        )

    except Exception as exc:
        logger.warning("Response generator failed (%s) — using template fallback.", exc)
        return GeneratedResponse(
            content=_FALLBACK_TEMPLATES.get(category, _FALLBACK_TEMPLATES[TicketCategory.UNKNOWN]),
            requires_review=True,
            tone=tone,
            used_fallback=True,
        )
