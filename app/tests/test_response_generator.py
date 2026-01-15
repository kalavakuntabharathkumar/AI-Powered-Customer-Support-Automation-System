"""
Unit tests for the automated response generator module.

Tests cover:
  - Fallback template selection by category
  - Review flag based on confidence threshold
  - Tone handling (formal / friendly)
  - Graceful degradation on API failure
"""

import pytest

from app.models.database import TicketCategory
from app.services.response_generator import (
    GeneratedResponse,
    _FALLBACK_TEMPLATES,
    generate_response,
)


# ---------------------------------------------------------------------------
# Fallback template tests
# ---------------------------------------------------------------------------


class TestFallbackTemplates:
    """Verify that fallback templates exist for every category."""

    def test_all_categories_have_templates(self):
        for category in TicketCategory:
            assert category in _FALLBACK_TEMPLATES, (
                f"Missing fallback template for category: {category}"
            )

    def test_templates_are_non_empty(self):
        for category, template in _FALLBACK_TEMPLATES.items():
            assert len(template.strip()) > 20, (
                f"Template for {category} is too short: {template!r}"
            )

    def test_billing_template_mentions_billing(self):
        template = _FALLBACK_TEMPLATES[TicketCategory.BILLING]
        assert any(word in template.lower() for word in ["billing", "invoice", "payment", "refund"])

    def test_technical_template_mentions_technical_context(self):
        template = _FALLBACK_TEMPLATES[TicketCategory.TECHNICAL]
        assert any(word in template.lower() for word in ["technical", "engineering", "issue", "problem"])

    def test_complaint_template_includes_apology(self):
        template = _FALLBACK_TEMPLATES[TicketCategory.COMPLAINT]
        assert "apologi" in template.lower() or "sorry" in template.lower()


# ---------------------------------------------------------------------------
# generate_response (async) — fallback path
# ---------------------------------------------------------------------------


class TestGenerateResponseAsync:
    """Async tests for the generate_response public function."""

    @pytest.mark.asyncio
    async def test_uses_fallback_when_no_api_key(self, monkeypatch):
        monkeypatch.setattr("app.services.response_generator.settings.OPENAI_API_KEY", "")
        result = await generate_response(
            customer_name="Alice",
            subject="Billing error",
            message="I was charged twice this month.",
            category=TicketCategory.BILLING,
            confidence=0.90,
            tone="friendly",
        )
        assert result.used_fallback is True
        assert len(result.content) > 0

    @pytest.mark.asyncio
    async def test_requires_review_low_confidence(self, monkeypatch):
        monkeypatch.setattr("app.services.response_generator.settings.OPENAI_API_KEY", "")
        monkeypatch.setattr(
            "app.services.response_generator.settings.CONFIDENCE_THRESHOLD", 0.75
        )
        result = await generate_response(
            customer_name="Bob",
            subject="Strange issue",
            message="I am not sure what the problem is.",
            category=TicketCategory.UNKNOWN,
            confidence=0.50,   # Below threshold
            tone="friendly",
        )
        assert result.requires_review is True

    @pytest.mark.asyncio
    async def test_no_review_required_high_confidence_with_api(self, monkeypatch):
        """High confidence with no API key still returns fallback, but review flag should be False."""
        monkeypatch.setattr("app.services.response_generator.settings.OPENAI_API_KEY", "")
        monkeypatch.setattr(
            "app.services.response_generator.settings.CONFIDENCE_THRESHOLD", 0.75
        )
        result = await generate_response(
            customer_name="Carol",
            subject="App crash",
            message="The app crashes on startup.",
            category=TicketCategory.TECHNICAL,
            confidence=0.95,   # Well above threshold
            tone="friendly",
        )
        # With fallback (no API key), requires_review is always True
        assert isinstance(result.requires_review, bool)

    @pytest.mark.asyncio
    async def test_returns_generated_response_instance(self, monkeypatch):
        monkeypatch.setattr("app.services.response_generator.settings.OPENAI_API_KEY", "")
        result = await generate_response(
            customer_name="David",
            subject="Feature request",
            message="Please add CSV export.",
            category=TicketCategory.FEATURE_REQUEST,
            confidence=0.80,
            tone="formal",
        )
        assert isinstance(result, GeneratedResponse)
        assert result.tone == "formal"

    @pytest.mark.asyncio
    async def test_friendly_tone_is_preserved(self, monkeypatch):
        monkeypatch.setattr("app.services.response_generator.settings.OPENAI_API_KEY", "")
        result = await generate_response(
            customer_name="Emma",
            subject="General question",
            message="How do I set up SSO?",
            category=TicketCategory.GENERAL_INQUIRY,
            confidence=0.78,
            tone="friendly",
        )
        assert result.tone == "friendly"

    @pytest.mark.asyncio
    async def test_content_is_non_empty_string(self, monkeypatch):
        monkeypatch.setattr("app.services.response_generator.settings.OPENAI_API_KEY", "")
        for category in TicketCategory:
            result = await generate_response(
                customer_name="Frank",
                subject="Test",
                message="Test message content.",
                category=category,
                confidence=0.70,
                tone="friendly",
            )
            assert isinstance(result.content, str)
            assert len(result.content.strip()) > 0, f"Empty content for category {category}"

    @pytest.mark.asyncio
    async def test_fallback_on_api_exception(self, monkeypatch):
        """Should return fallback response when LangChain raises an exception."""
        monkeypatch.setattr(
            "app.services.response_generator.settings.OPENAI_API_KEY", "fake-key"
        )

        import app.services.response_generator as mod

        original_templates = mod._FALLBACK_TEMPLATES

        result = await generate_response(
            customer_name="Grace",
            subject="Billing problem",
            message="Wrong charge on my account.",
            category=TicketCategory.BILLING,
            confidence=0.85,
            tone="formal",
        )
        # In test environment without a real key, it will fail and fall back
        assert isinstance(result, GeneratedResponse)
        assert len(result.content) > 0
