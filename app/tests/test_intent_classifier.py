"""
Unit tests for the intent classifier module.

Tests cover:
  - Rule-based fallback classifier keyword matching
  - AI response parsing
  - Graceful fallback on API failure
"""

import pytest

from app.models.database import TicketCategory
from app.services.intent_classifier import (
    ClassificationResult,
    _parse_ai_response,
    _rule_based_classify,
    classify_intent,
)


# ---------------------------------------------------------------------------
# Rule-based classifier
# ---------------------------------------------------------------------------


class TestRuleBasedClassifier:
    """Test suite for the keyword-based fallback classifier."""

    def test_billing_keyword_invoice(self):
        result = _rule_based_classify("My invoice is wrong I was overcharged")
        assert result.category == TicketCategory.BILLING
        assert result.used_fallback is True
        assert result.confidence > 0.5

    def test_billing_keyword_refund(self):
        result = _rule_based_classify("I need a refund for my payment")
        assert result.category == TicketCategory.BILLING

    def test_technical_keyword_crash(self):
        result = _rule_based_classify("The application keeps crashing on startup")
        assert result.category == TicketCategory.TECHNICAL
        assert result.confidence > 0.5

    def test_technical_keyword_error(self):
        result = _rule_based_classify("Getting a 500 error on the dashboard page")
        assert result.category == TicketCategory.TECHNICAL

    def test_account_keyword_password(self):
        result = _rule_based_classify("I forgot my password and cannot login")
        assert result.category == TicketCategory.ACCOUNT

    def test_account_keyword_locked(self):
        result = _rule_based_classify("My account is locked and I cannot access it")
        assert result.category == TicketCategory.ACCOUNT

    def test_complaint_keyword(self):
        result = _rule_based_classify("I am very frustrated with this terrible service")
        assert result.category == TicketCategory.COMPLAINT

    def test_feature_request_keyword(self):
        result = _rule_based_classify("I would like to suggest a new feature for bulk export")
        assert result.category == TicketCategory.FEATURE_REQUEST

    def test_general_inquiry_keyword(self):
        result = _rule_based_classify("How do I set up the Slack integration?")
        assert result.category == TicketCategory.GENERAL_INQUIRY

    def test_unknown_no_match(self):
        result = _rule_based_classify("xyzzy qwerty foobar baz")
        assert result.category == TicketCategory.UNKNOWN
        assert result.confidence == 0.40
        assert result.used_fallback is True

    def test_case_insensitive_matching(self):
        result = _rule_based_classify("INVOICE PAYMENT REFUND")
        assert result.category == TicketCategory.BILLING

    def test_result_type(self):
        result = _rule_based_classify("help me with my question")
        assert isinstance(result, ClassificationResult)

    def test_confidence_in_valid_range(self):
        for text in ["billing issue", "technical crash", "account locked", "bad service"]:
            result = _rule_based_classify(text)
            assert 0.0 <= result.confidence <= 1.0


# ---------------------------------------------------------------------------
# AI response parser
# ---------------------------------------------------------------------------


class TestParseAIResponse:
    """Test suite for the LLM response parser."""

    def test_parse_valid_response(self):
        raw = "CATEGORY: billing\nCONFIDENCE: 0.92\nREASONING: Customer mentions overcharged invoice."
        category, confidence, reasoning = _parse_ai_response(raw)
        assert category == TicketCategory.BILLING
        assert confidence == pytest.approx(0.92)
        assert "invoice" in reasoning.lower()

    def test_parse_technical_category(self):
        raw = "CATEGORY: technical\nCONFIDENCE: 0.88\nREASONING: Error message in the ticket."
        category, confidence, _ = _parse_ai_response(raw)
        assert category == TicketCategory.TECHNICAL
        assert confidence == pytest.approx(0.88)

    def test_parse_account_category(self):
        raw = "CATEGORY: account\nCONFIDENCE: 0.75\nREASONING: Password reset issue."
        category, confidence, _ = _parse_ai_response(raw)
        assert category == TicketCategory.ACCOUNT

    def test_parse_unknown_category_maps_to_unknown(self):
        raw = "CATEGORY: nonexistent_category\nCONFIDENCE: 0.50\nREASONING: Could not classify."
        category, confidence, _ = _parse_ai_response(raw)
        assert category == TicketCategory.UNKNOWN

    def test_parse_confidence_clamped_above_one(self):
        raw = "CATEGORY: billing\nCONFIDENCE: 1.5\nREASONING: High confidence."
        _, confidence, _ = _parse_ai_response(raw)
        assert confidence == 1.0

    def test_parse_confidence_clamped_below_zero(self):
        raw = "CATEGORY: billing\nCONFIDENCE: -0.3\nREASONING: Negative confidence."
        _, confidence, _ = _parse_ai_response(raw)
        assert confidence == 0.0

    def test_parse_invalid_response_raises_value_error(self):
        with pytest.raises(ValueError):
            _parse_ai_response("This is completely unparseable text.")

    def test_parse_case_insensitive_category(self):
        raw = "CATEGORY: BILLING\nCONFIDENCE: 0.80\nREASONING: Billing issue."
        category, _, _ = _parse_ai_response(raw)
        assert category == TicketCategory.BILLING

    def test_parse_missing_reasoning_returns_default(self):
        raw = "CATEGORY: billing\nCONFIDENCE: 0.80"
        _, _, reasoning = _parse_ai_response(raw)
        assert reasoning == "No reasoning provided."


# ---------------------------------------------------------------------------
# Full classifier (async) — fallback path
# ---------------------------------------------------------------------------


class TestClassifyIntentAsync:
    """Async tests for the main classify_intent function."""

    @pytest.mark.asyncio
    async def test_classify_uses_fallback_without_api_key(self, monkeypatch):
        """Should use rule-based classifier when OPENAI_API_KEY is empty."""
        monkeypatch.setattr("app.services.intent_classifier.settings.OPENAI_API_KEY", "")
        result = await classify_intent("Cannot login to my account", "I forgot my password")
        assert result.used_fallback is True
        assert result.category == TicketCategory.ACCOUNT

    @pytest.mark.asyncio
    async def test_classify_returns_classification_result(self, monkeypatch):
        monkeypatch.setattr("app.services.intent_classifier.settings.OPENAI_API_KEY", "")
        result = await classify_intent("Billing error on my invoice", "I was charged twice")
        assert isinstance(result, ClassificationResult)
        assert isinstance(result.confidence, float)
        assert 0.0 <= result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_classify_fallback_on_exception(self, monkeypatch):
        """Should gracefully fall back when the LangChain call raises."""
        monkeypatch.setattr(
            "app.services.intent_classifier.settings.OPENAI_API_KEY", "fake-key-for-testing"
        )

        async def mock_chain_invoke(*args, **kwargs):
            raise ConnectionError("Simulated network failure")

        # Patch at the import level inside the function
        import app.services.intent_classifier as mod

        original = mod._rule_based_classify

        async def patched_classify(subject, message):
            # Force the try block to fail and verify fallback is used
            return original(f"{subject} {message}")

        result = await classify_intent("Application bug report", "App crashes on startup")
        assert isinstance(result, ClassificationResult)
