"""Tests for app/scraping/campaigns.py's deterministic banner detection and
the LLM-normalization fallback for ambiguous promo language (mocked out —
these tests never call the real API).
"""

from unittest.mock import AsyncMock, patch

from app.schemas.campaign import DetectedCampaign
from app.scraping.campaigns import detect_campaigns_deterministic, discover_campaigns


class TestDetectCampaignsDeterministic:
    def test_percent_off_banner_is_parsed_directly(self):
        html = '<div class="announcement-bar">Spring Sale: 20% off everything!</div>'
        confident, ambiguous = detect_campaigns_deterministic(html, "https://example.com")
        assert len(confident) == 1
        assert "20% off" in confident[0].discount_text
        assert ambiguous == []

    def test_dollar_off_and_coupon_code_are_both_captured(self):
        html = '<div class="promo-banner">Use code SAVE10 for $10 off your order</div>'
        confident, _ambiguous = detect_campaigns_deterministic(html, "https://example.com")
        assert len(confident) == 1
        assert "$10 off" in confident[0].discount_text
        assert "SAVE10" in confident[0].discount_text

    def test_promo_language_without_parseable_amount_is_ambiguous(self):
        html = '<div class="hero-banner">Big Clearance Event — This Weekend Only!</div>'
        confident, ambiguous = detect_campaigns_deterministic(html, "https://example.com")
        assert confident == []
        assert len(ambiguous) == 1

    def test_non_banner_elements_are_ignored(self):
        html = '<div class="footer">Copyright 2026. See our sale page for 20% off deals.</div>'
        confident, ambiguous = detect_campaigns_deterministic(html, "https://example.com")
        assert confident == []
        assert ambiguous == []

    def test_no_discount_language_yields_nothing(self):
        html = '<div class="hero-banner">Welcome to our store!</div>'
        confident, ambiguous = detect_campaigns_deterministic(html, "https://example.com")
        assert confident == []
        assert ambiguous == []


class TestDiscoverCampaigns:
    async def test_no_llm_call_when_everything_is_confidently_parsed(self):
        html = '<div class="announcement-bar">30% off sitewide</div>'
        with patch("app.scraping.campaigns._normalize_with_llm", new_callable=AsyncMock) as mock_llm:
            result = await discover_campaigns(html, "https://example.com")
        mock_llm.assert_not_awaited()
        assert len(result) == 1

    async def test_llm_normalizes_ambiguous_banner_text(self):
        html = '<div class="hero-banner">Big Clearance Event — This Weekend Only!</div>'
        with patch("app.scraping.campaigns._normalize_with_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = DetectedCampaign(
                title="Clearance Event",
                description="A weekend clearance event.",
                discount_text="Clearance",
                source_url="https://example.com",
            )
            result = await discover_campaigns(html, "https://example.com")
        mock_llm.assert_awaited_once()
        assert len(result) == 1
        assert result[0].title == "Clearance Event"

    async def test_llm_declining_to_find_a_real_offer_yields_nothing(self):
        html = '<div class="hero-banner">Big Clearance Event — This Weekend Only!</div>'
        with patch("app.scraping.campaigns._normalize_with_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = None
            result = await discover_campaigns(html, "https://example.com")
        assert result == []

    async def test_empty_html_returns_nothing_without_llm_call(self):
        with patch("app.scraping.campaigns._normalize_with_llm", new_callable=AsyncMock) as mock_llm:
            result = await discover_campaigns("", "https://example.com")
        mock_llm.assert_not_awaited()
        assert result == []
