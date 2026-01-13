"""
Intent Classifier Module
========================
Classifies incoming support tickets into predefined categories using LangChain + OpenAI.
Falls back to a rule-based classifier when the OpenAI API is unavailable.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.core.config import settings
from app.models.database import TicketCategory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ClassificationResult:
    """
    Result produced by the intent classifier.

    Attributes:
        category: The predicted ticket category.
        confidence: Float in [0, 1] representing classification certainty.
        used_fallback: True when the rule-based classifier was used instead of AI.
        reasoning: Optional explanation returned by the AI model.
    """

    category: TicketCategory
    confidence: float
    used_fallback: bool = False
    reasoning: Optional[str] = None


# ---------------------------------------------------------------------------
# Rule-based fallback classifier
# ---------------------------------------------------------------------------

# Keyword patterns mapped to ticket categories (ordered by specificity)
_RULE_PATTERNS: list[tuple[list[str], TicketCategory, float]] = [
    (
        ["invoice", "bill", "charge", "payment", "refund", "subscription", "price", "cost", "fee", "overcharged"],
        TicketCategory.BILLING,
        0.70,
    ),
    (
        ["error", "bug", "crash", "broken", "not working", "issue", "problem", "fail", "500", "exception", "timeout", "slow"],
        TicketCategory.TECHNICAL,
        0.70,
    ),
    (
        ["password", "login", "account", "username", "email", "profile", "access", "locked", "sign in", "signup", "register"],
        TicketCategory.ACCOUNT,
        0.70,
    ),
    (
        ["unhappy", "disappointed", "unacceptable", "terrible", "awful", "worst", "complaint", "frustrated", "angry"],
        TicketCategory.COMPLAINT,
        0.68,
    ),
    (
        ["feature", "suggestion", "would be nice", "request", "add", "improve", "wish", "could you", "can you add"],
        TicketCategory.FEATURE_REQUEST,
        0.65,
    ),
    (
        ["how", "what", "when", "where", "why", "help", "guide", "tutorial", "documentation", "faq", "question"],
        TicketCategory.GENERAL_INQUIRY,
        0.60,
    ),
]


def _rule_based_classify(text: str) -> ClassificationResult:
    """
    Classify ticket text using keyword pattern matching.

    Iterates through ranked rule patterns and returns the first match.
    Falls back to UNKNOWN when no pattern matches.

    Args:
        text: Combined ticket subject and message text.

    Returns:
        ClassificationResult with used_fallback=True.
    """
    normalised = text.lower()

    for keywords, category, confidence in _RULE_PATTERNS:
        if any(kw in normalised for kw in keywords):
            logger.debug("Rule-based match: category=%s", category)
            return ClassificationResult(
                category=category,
                confidence=confidence,
                used_fallback=True,
                reasoning="Classified by rule-based keyword matching (fallback).",
            )

    return ClassificationResult(
        category=TicketCategory.UNKNOWN,
        confidence=0.40,
        used_fallback=True,
        reasoning="No keyword pattern matched; defaulting to UNKNOWN.",
    )


# ---------------------------------------------------------------------------
# AI-based classifier (LangChain + OpenAI)
# ---------------------------------------------------------------------------

_CLASSIFICATION_PROMPT = """You are a customer support triage specialist. Classify the following support ticket into exactly one of these categories:

Categories:
- billing       → payment issues, invoices, refunds, subscription charges
- technical     → bugs, errors, crashes, performance problems, integration failures
- account       → login, password reset, profile changes, access control
- general_inquiry → general questions, how-to requests, documentation queries
- complaint     → expressions of dissatisfaction without a specific technical issue
- feature_request → requests for new features or product improvements
- unknown       → cannot be determined from the available information

Ticket subject: {subject}
Ticket message: {message}

Respond in this exact format (no extra text):
CATEGORY: <category>
CONFIDENCE: <float between 0.0 and 1.0>
REASONING: <one-sentence explanation>"""


def _parse_ai_response(raw: str) -> tuple[TicketCategory, float, str]:
    """
    Parse the structured text response from the LLM.

    Args:
        raw: Raw string returned by the language model.

    Returns:
        Tuple of (category, confidence, reasoning).

    Raises:
        ValueError: When the response cannot be parsed.
    """
    category_match = re.search(r"CATEGORY:\s*(\w+)", raw, re.IGNORECASE)
    confidence_match = re.search(r"CONFIDENCE:\s*([\d.]+)", raw, re.IGNORECASE)
    reasoning_match = re.search(r"REASONING:\s*(.+)", raw, re.IGNORECASE | re.DOTALL)

    if not category_match or not confidence_match:
        raise ValueError(f"Could not parse AI response: {raw!r}")

    raw_category = category_match.group(1).lower().strip()
    try:
        category = TicketCategory(raw_category)
    except ValueError:
        category = TicketCategory.UNKNOWN

    try:
        confidence = max(0.0, min(1.0, float(confidence_match.group(1))))
    except ValueError:
        confidence = 0.5

    reasoning = reasoning_match.group(1).strip() if reasoning_match else "No reasoning provided."

    return category, confidence, reasoning


async def classify_intent(subject: str, message: str) -> ClassificationResult:
    """
    Classify the intent of a support ticket.

    Attempts AI classification first; falls back to rule-based matching on any error.

    Args:
        subject: Ticket subject line.
        message: Full ticket message body.

    Returns:
        ClassificationResult with category, confidence, and optional reasoning.
    """
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY is not set — using rule-based fallback classifier.")
        return _rule_based_classify(f"{subject} {message}")

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import PromptTemplate
        from langchain_core.output_parsers import StrOutputParser

        llm = ChatOpenAI(
            model=settings.OPENAI_MODEL,
            temperature=0.0,   # Deterministic output for classification
            max_tokens=256,
            api_key=settings.OPENAI_API_KEY,
        )

        prompt = PromptTemplate.from_template(_CLASSIFICATION_PROMPT)
        chain = prompt | llm | StrOutputParser()

        raw_output: str = await chain.ainvoke({"subject": subject, "message": message})
        category, confidence, reasoning = _parse_ai_response(raw_output)

        logger.info("AI classification → category=%s confidence=%.2f", category, confidence)
        return ClassificationResult(
            category=category,
            confidence=confidence,
            used_fallback=False,
            reasoning=reasoning,
        )

    except Exception as exc:
        logger.warning("AI classifier failed (%s) — switching to rule-based fallback.", exc)
        return _rule_based_classify(f"{subject} {message}")
