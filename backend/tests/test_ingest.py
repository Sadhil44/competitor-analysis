"""Tests for the scraping pipeline's pagination-stopping logic
(app/scraping/ingest.py). fetch_page and extract_products_merged are
mocked — these tests cover ingest_page's control flow (when it keeps
paginating vs. stops), not real scraping or LLM extraction.
"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import Campaign, Product
from app.schemas.campaign import DetectedCampaign
from app.scraping.extractor import ExtractedProduct, ExtractedProductList
from app.scraping.fetcher import FetchedPage
from app.scraping.ingest import _persist_campaign, _price_context_fingerprint, ingest_page


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
    return FetchedPage(url="https://acme.example/catalog", html="", text=text, next_page_url=next_url, fetched_via="http")


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


def _detected(title: str, discount_text: str) -> DetectedCampaign:
    return DetectedCampaign(
        title=title, description=title, discount_text=discount_text, source_url="https://acme.example"
    )


class TestPersistCampaign:
    """Regression coverage for a real issue found live: the same sitewide
    banner gets LLM-normalized into a differently-worded title nearly every
    time it's seen, so deduping on an exact title match let 26 near-
    duplicate rows through for one banner in a single crawl. Dedup now
    keys on (competitor, product, discount_text) instead.
    """

    async def test_same_discount_text_different_titles_is_deduped(self, db_session, competitor):
        first = await _persist_campaign(db_session, competitor.id, _detected("Welcome to Acme", "Free shipping"))
        second = await _persist_campaign(db_session, competitor.id, _detected("Acme Relaunch!", "Free shipping"))
        await db_session.commit()

        assert first is True
        assert second is False
        result = await db_session.execute(select(Campaign).where(Campaign.competitor_id == competitor.id))
        assert len(result.scalars().all()) == 1

    async def test_different_discount_text_is_not_deduped(self, db_session, competitor):
        first = await _persist_campaign(db_session, competitor.id, _detected("Sale", "20% off"))
        second = await _persist_campaign(db_session, competitor.id, _detected("Sale", "Free shipping"))
        await db_session.commit()

        assert first is True
        assert second is True

    async def test_same_discount_text_different_products_is_not_deduped(self, db_session, competitor):
        product_a = Product(competitor_id=competitor.id, name="Product A", url="")
        product_b = Product(competitor_id=competitor.id, name="Product B", url="")
        db_session.add_all([product_a, product_b])
        await db_session.flush()

        first = await _persist_campaign(
            db_session, competitor.id, _detected("Sale", "10% off"), product_id=product_a.id
        )
        second = await _persist_campaign(
            db_session, competitor.id, _detected("Sale", "10% off"), product_id=product_b.id
        )
        await db_session.commit()

        assert first is True
        assert second is True


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


async def test_collects_product_links_found_on_the_page(db_session, competitor):
    html = '<a href="/products/widget">Widget</a><a href="/collections/all">All</a>'
    page = FetchedPage(url="https://acme.example/catalog", html=html, text="Widget $9.99", next_page_url=None, fetched_via="http")
    with (
        patch("app.scraping.ingest.fetch_page", new_callable=AsyncMock) as mock_fetch,
        patch("app.scraping.ingest.extract_products_merged", new_callable=AsyncMock) as mock_extract,
    ):
        mock_fetch.return_value = page
        mock_extract.return_value = _products("Widget")

        result = await ingest_page(db_session, competitor.slug, "https://acme.example/catalog")

    assert result.product_links == {"https://acme.example/products/widget"}


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


def _page_with_links(links: list[str], next_url: str | None, filler: str = "aaaa") -> FetchedPage:
    """A page whose own extraction finds nothing (no JSON-LD/microdata on
    a typical listing page), but which links to real product pages —
    the case that used to stop pagination prematurely. `filler` varies the
    price-context fingerprint between pages so the recycled-pagination
    guard (see PRICE_CONTEXT_SIMILARITY_THRESHOLD) doesn't itself stop the
    loop before product_links gets a chance to matter.
    """
    html = "".join(f'<a href="{link}">item</a>' for link in links)
    return FetchedPage(
        url="https://acme.example/catalog", html=html, text=_page_text("$9.99", filler), next_page_url=next_url, fetched_via="http"
    )


async def test_continues_pagination_when_page_has_product_links_but_no_extracted_products(db_session, competitor):
    """A collection page can legitimately extract zero products from its
    own content (no inline JSON-LD/microdata) while still linking to real
    product pages — pagination must not stop just because new_items was
    empty if the page contributed new product_links.
    """
    with (
        patch("app.scraping.ingest.fetch_page", new_callable=AsyncMock) as mock_fetch,
        patch("app.scraping.ingest.extract_products_merged", new_callable=AsyncMock) as mock_extract,
    ):
        mock_fetch.side_effect = [
            _page_with_links(["/products/a"], "https://acme.example/catalog?page=2", filler="aaaa"),
            _page_with_links(["/products/b"], None, filler="bbbb"),
        ]
        mock_extract.return_value = _products()  # empty — nothing extracted from the listing itself

        result = await ingest_page(db_session, competitor.slug, "https://acme.example/catalog?page=1")

    assert mock_fetch.await_count == 2
    assert result.product_links == {
        "https://acme.example/products/a",
        "https://acme.example/products/b",
    }


async def test_stops_when_a_page_has_neither_new_products_nor_new_links(db_session, competitor):
    with (
        patch("app.scraping.ingest.fetch_page", new_callable=AsyncMock) as mock_fetch,
        patch("app.scraping.ingest.extract_products_merged", new_callable=AsyncMock) as mock_extract,
    ):
        mock_fetch.return_value = _page_with_links([], "https://acme.example/catalog?page=2")
        mock_extract.return_value = _products()

        await ingest_page(db_session, competitor.slug, "https://acme.example/catalog?page=1")

    assert mock_fetch.await_count == 1


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
