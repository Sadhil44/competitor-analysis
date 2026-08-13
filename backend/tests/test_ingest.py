"""Tests for the scraping pipeline's pagination-stopping logic
(app/scraping/ingest.py). fetch_page and extract_products_merged are
mocked — these tests cover ingest_page's control flow (when it keeps
paginating vs. stops), not real scraping or LLM extraction.
"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import Product
from app.scraping.extractor import ExtractedProduct, ExtractedProductList
from app.scraping.fetcher import FetchedPage
from app.scraping.ingest import _price_context_fingerprint, ingest_page


class TestPriceContextFingerprint:
    def test_extracts_window_around_dollar_sign(self):
        assert "$19.99" in _price_context_fingerprint("Item A $19.99 in stock")

    def test_no_prices_is_empty(self):
        assert _price_context_fingerprint("no prices on this page") == ""

    def test_multiple_prices_are_space_joined(self):
        text = "$1" + ("x" * 100) + "$2"
        fp = _price_context_fingerprint(text)
        assert fp.count("$") == 2


def _page(text: str, next_url: str | None) -> FetchedPage:
    return FetchedPage(text=text, next_page_url=next_url)


def _products(*names: str) -> ExtractedProductList:
    return ExtractedProductList(
        products=[ExtractedProduct(name=n, price=1, currency="USD", in_stock=True) for n in names]
    )


# The similarity guard compares 40-char windows around each "$" (see
# PRICE_CONTEXT_WINDOW in ingest.py). Distinct filler text on either side of
# the price keeps two "really different" pages' fingerprints well under the
# 0.5 similarity threshold, instead of leaving it to chance with short
# literal strings that happen to share a lot of characters.
def _page_text(price: str, filler: str) -> str:
    return f"{filler * 10} {price} {filler * 10}"


@pytest_asyncio.fixture
async def competitor(competitor_factory):
    return await competitor_factory(name="Acme", website_url="https://acme.example")


async def test_stops_when_no_next_link(db_session, competitor):
    with (
        patch("app.scraping.ingest.fetch_page", new_callable=AsyncMock) as mock_fetch,
        patch("app.scraping.ingest.extract_products_merged", new_callable=AsyncMock) as mock_extract,
    ):
        mock_fetch.return_value = _page(_page_text("$9.99", "aaaa"), None)
        mock_extract.return_value = _products("Widget")

        await ingest_page(db_session, competitor.slug, "https://acme.example/catalog")

    assert mock_fetch.await_count == 1
    result = await db_session.execute(select(Product).where(Product.competitor_id == competitor.id))
    assert {p.name for p in result.scalars()} == {"Widget"}


async def test_stops_when_revisiting_a_url(db_session, competitor):
    """A "Next" link pointing back to a page already fetched (e.g. one that
    stays present past the real last page) must not loop forever."""
    start_url = "https://acme.example/catalog"
    with (
        patch("app.scraping.ingest.fetch_page", new_callable=AsyncMock) as mock_fetch,
        patch("app.scraping.ingest.extract_products_merged", new_callable=AsyncMock) as mock_extract,
    ):
        mock_fetch.return_value = _page(_page_text("$9.99", "aaaa"), start_url)  # "next" == itself
        mock_extract.return_value = _products("Widget")

        await ingest_page(db_session, competitor.slug, start_url)

    assert mock_fetch.await_count == 1


async def test_stops_on_recycled_pagination_content(db_session, competitor):
    """A fake next-link that keeps incrementing while re-serving the same
    underlying catalog content (seen on Holland Bulb Farms) is detected via
    price-context similarity, not by comparing URLs or whole-page text."""
    same_text = _page_text("$9.99", "aaaa")
    with (
        patch("app.scraping.ingest.fetch_page", new_callable=AsyncMock) as mock_fetch,
        patch("app.scraping.ingest.extract_products_merged", new_callable=AsyncMock) as mock_extract,
    ):
        mock_fetch.side_effect = [
            _page(same_text, "https://acme.example/catalog?page=2"),
            _page(same_text, "https://acme.example/catalog?page=3"),
        ]
        mock_extract.return_value = _products("Widget")

        await ingest_page(db_session, competitor.slug, "https://acme.example/catalog?page=1")

    assert mock_fetch.await_count == 2
    # Page 2's near-identical price content stops the loop before it's ever
    # extracted.
    assert mock_extract.await_count == 1


async def test_stops_when_no_new_products_found(db_session, competitor):
    with (
        patch("app.scraping.ingest.fetch_page", new_callable=AsyncMock) as mock_fetch,
        patch("app.scraping.ingest.extract_products_merged", new_callable=AsyncMock) as mock_extract,
    ):
        mock_fetch.side_effect = [
            _page(_page_text("$9.99", "aaaa"), "https://acme.example/catalog?page=2"),
            _page(_page_text("$19.99", "bbbb"), "https://acme.example/catalog?page=3"),
        ]
        # Page 2 reports the same product already seen on page 1 — nothing new.
        mock_extract.side_effect = [_products("Widget"), _products("Widget")]

        await ingest_page(db_session, competitor.slug, "https://acme.example/catalog?page=1")

    assert mock_fetch.await_count == 2
    assert mock_extract.await_count == 2
    result = await db_session.execute(select(Product).where(Product.competitor_id == competitor.id))
    assert {p.name for p in result.scalars()} == {"Widget"}


async def test_follows_real_multi_page_pagination(db_session, competitor):
    with (
        patch("app.scraping.ingest.fetch_page", new_callable=AsyncMock) as mock_fetch,
        patch("app.scraping.ingest.extract_products_merged", new_callable=AsyncMock) as mock_extract,
    ):
        mock_fetch.side_effect = [
            _page(_page_text("$9.99", "aaaa"), "https://acme.example/catalog?page=2"),
            _page(_page_text("$19.99", "bbbb"), None),
        ]
        mock_extract.side_effect = [_products("Widget"), _products("Gadget")]

        await ingest_page(db_session, competitor.slug, "https://acme.example/catalog?page=1")

    assert mock_fetch.await_count == 2
    assert mock_extract.await_count == 2
    result = await db_session.execute(select(Product).where(Product.competitor_id == competitor.id))
    assert {p.name for p in result.scalars()} == {"Widget", "Gadget"}


async def test_raises_for_unknown_competitor(db_session):
    with pytest.raises(ValueError):
        await ingest_page(db_session, "does-not-exist", "https://example.com")
