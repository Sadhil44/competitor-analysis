"""Tests for the deterministic extraction layers in
app/scraping/extractor.py — JSON-LD (all documented shapes), embedded
Shopify ProductJson state, the generic HTML fallback, and the top-level
routing that only calls the LLM when nothing deterministic was found (the
LLM call itself is mocked out; these tests never hit the real API).
"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

from bs4 import BeautifulSoup

from app.schemas.extraction import ExtractedProductList
from app.scraping.extractor import (
    _extract_from_embedded_state,
    _extract_from_generic_html,
    _extract_from_jsonld,
    _extract_from_microdata,
    _parse_availability,
    _parse_price_value,
    extract_products_merged,
)
from app.scraping.fetcher import FetchedPage


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


class TestParsePriceValue:
    def test_plain_float(self):
        assert _parse_price_value(19.99) == Decimal("19.99")

    def test_plain_int(self):
        assert _parse_price_value(20) == Decimal(20)

    def test_currency_symbol_string(self):
        assert _parse_price_value("$19.99") == Decimal("19.99")

    def test_thousands_separator(self):
        assert _parse_price_value("$1,234.56") == Decimal("1234.56")

    def test_currency_code_prefix(self):
        assert _parse_price_value("USD 19.99") == Decimal("19.99")

    def test_non_numeric_text_returns_none(self):
        assert _parse_price_value("call for price") is None

    def test_none_input_returns_none(self):
        assert _parse_price_value(None) is None

    def test_unit_price_prefix_does_not_shadow_real_price(self):
        # Regression: Shopify's unit-price convention renders a product
        # card's price block as one concatenated string like this — a bare
        # first-digit-sequence search finds "1" (from "1 for") before it
        # ever reaches the real price. Found live on gardeners.com.
        assert _parse_price_value("1 for$149.99Unit price/per") == Decimal("149.99")

    def test_price_range_uses_first_symbol_anchored_price(self):
        assert _parse_price_value("$19.99 - $29.99") == Decimal("19.99")


class TestParseAvailability:
    def test_in_stock_schema_url(self):
        assert _parse_availability("https://schema.org/InStock") is True

    def test_out_of_stock_schema_url(self):
        assert _parse_availability("https://schema.org/OutOfStock") is False

    def test_sold_out(self):
        assert _parse_availability("https://schema.org/SoldOut") is False

    def test_missing_defaults_to_true(self):
        assert _parse_availability(None) is True


class TestExtractFromJsonld:
    def test_single_product_object_with_offer(self):
        html = """
        <script type="application/ld+json">
        {"@type": "Product", "name": "Tulip Bulb", "sku": "TB-1",
         "offers": {"@type": "Offer", "price": "19.99", "priceCurrency": "USD",
                    "availability": "https://schema.org/InStock"}}
        </script>
        """
        products = _extract_from_jsonld(_soup(html), "https://example.com/p")
        assert len(products) == 1
        assert products[0].name == "Tulip Bulb"
        assert products[0].sku == "TB-1"
        assert products[0].price == Decimal("19.99")
        assert products[0].currency == "USD"
        assert products[0].in_stock is True

    def test_list_of_product_objects(self):
        html = """
        <script type="application/ld+json">
        [{"@type": "Product", "name": "A", "offers": {"price": 10}},
         {"@type": "Product", "name": "B", "offers": {"price": 20}}]
        </script>
        """
        products = _extract_from_jsonld(_soup(html), "https://example.com/p")
        assert {p.name for p in products} == {"A", "B"}

    def test_graph_wrapper(self):
        html = """
        <script type="application/ld+json">
        {"@graph": [{"@type": "Product", "name": "A", "offers": {"price": 10}},
                    {"@type": "BreadcrumbList", "name": "nav"}]}
        </script>
        """
        products = _extract_from_jsonld(_soup(html), "https://example.com/p")
        assert len(products) == 1
        assert products[0].name == "A"

    def test_aggregate_offer_uses_low_price(self):
        html = """
        <script type="application/ld+json">
        {"@type": "Product", "name": "A",
         "offers": {"@type": "AggregateOffer", "lowPrice": 15, "highPrice": 25, "priceCurrency": "USD"}}
        </script>
        """
        products = _extract_from_jsonld(_soup(html), "https://example.com/p")
        assert products[0].price == Decimal(15)

    def test_brand_object_and_image_list(self):
        html = """
        <script type="application/ld+json">
        {"@type": "Product", "name": "A", "brand": {"@type": "Brand", "name": "Acme"},
         "image": ["https://example.com/img.jpg", "https://example.com/img2.jpg"]}
        </script>
        """
        products = _extract_from_jsonld(_soup(html), "https://example.com/p")
        assert products[0].brand == "Acme"
        assert products[0].image_url == "https://example.com/img.jpg"

    def test_malformed_block_is_skipped_not_raised(self):
        html = '<script type="application/ld+json">{not valid json</script>'
        assert _extract_from_jsonld(_soup(html), "https://example.com/p") == []

    def test_non_product_type_is_ignored(self):
        html = '<script type="application/ld+json">{"@type": "BreadcrumbList", "name": "nav"}</script>'
        assert _extract_from_jsonld(_soup(html), "https://example.com/p") == []

    def test_no_offers_still_extracts_name(self):
        html = '<script type="application/ld+json">{"@type": "Product", "name": "No Price Item"}</script>'
        products = _extract_from_jsonld(_soup(html), "https://example.com/p")
        assert len(products) == 1
        assert products[0].price is None


class TestExtractFromMicrodata:
    def test_basic_product_with_offer(self):
        html = """
        <div itemscope itemtype="http://schema.org/Product">
          <span itemprop="name">Black Surprise Gladiolus</span>
          <span itemprop="sku">BSG-1</span>
          <div itemprop="offers" itemscope itemtype="http://schema.org/Offer">
            <span itemprop="price" content="21.95">$21.95</span>
            <meta itemprop="priceCurrency" content="USD">
            <link itemprop="availability" href="http://schema.org/InStock">
          </div>
        </div>
        """
        products = _extract_from_microdata(_soup(html), "https://example.com/p")
        assert len(products) == 1
        product = products[0]
        assert product.name == "Black Surprise Gladiolus"
        assert product.sku == "BSG-1"
        assert product.price == Decimal("21.95")
        assert product.currency == "USD"
        assert product.in_stock is True
        assert product.source == "microdata"

    def test_nested_offer_price_not_confused_with_outer_scope(self):
        """A price itemprop that lives inside the nested Offer scope must
        not leak out as if it were a top-level Product itemprop (and vice
        versa) — this is what _direct_itemprops' scoping guards against."""
        html = """
        <div itemscope itemtype="http://schema.org/Product">
          <span itemprop="name">Widget</span>
          <div itemprop="offers" itemscope itemtype="http://schema.org/Offer">
            <span itemprop="price" content="9.99"></span>
          </div>
        </div>
        """
        products = _extract_from_microdata(_soup(html), "https://example.com/p")
        assert products[0].price == Decimal("9.99")

    def test_out_of_stock_availability(self):
        html = """
        <div itemscope itemtype="http://schema.org/Product">
          <span itemprop="name">Widget</span>
          <div itemprop="offers" itemscope itemtype="http://schema.org/Offer">
            <link itemprop="availability" href="http://schema.org/OutOfStock">
          </div>
        </div>
        """
        products = _extract_from_microdata(_soup(html), "https://example.com/p")
        assert products[0].in_stock is False

    def test_no_name_yields_no_product(self):
        html = '<div itemscope itemtype="http://schema.org/Product"><span itemprop="sku">X</span></div>'
        assert _extract_from_microdata(_soup(html), "https://example.com/p") == []

    def test_non_product_itemtype_is_ignored(self):
        html = '<div itemscope itemtype="http://schema.org/BreadcrumbList"><span itemprop="name">nav</span></div>'
        assert _extract_from_microdata(_soup(html), "https://example.com/p") == []


class TestExtractFromEmbeddedState:
    def test_shopify_product_json(self):
        html = """
        <script type="application/json" id="ProductJson-product-template">
        {"title": "Rose Bush", "vendor": "Acme", "type": "Shrub",
         "variants": [{"price": 2999, "compare_at_price": 3999, "available": true, "sku": "RB-1"}],
         "featured_image": "https://example.com/rose.jpg", "description": "<p>Nice rose</p>"}
        </script>
        """
        products = _extract_from_embedded_state(_soup(html), "https://example.com/p")
        assert len(products) == 1
        product = products[0]
        assert product.name == "Rose Bush"
        assert product.price == Decimal("29.99")
        assert product.original_price == Decimal("39.99")
        assert product.brand == "Acme"
        assert product.sku == "RB-1"
        assert product.description == "Nice rose"

    def test_ignores_non_productjson_scripts(self):
        html = '<script type="application/json" id="other-data">{"foo": "bar"}</script>'
        assert _extract_from_embedded_state(_soup(html), "https://example.com/p") == []

    def test_no_markdown_when_compare_at_not_higher(self):
        html = """
        <script type="application/json" id="ProductJson-x">
        {"title": "A", "variants": [{"price": 1000, "compare_at_price": 1000, "available": true}]}
        </script>
        """
        products = _extract_from_embedded_state(_soup(html), "https://example.com/p")
        assert products[0].original_price is None

    def test_unavailable_variant(self):
        html = """
        <script type="application/json" id="ProductJson-x">
        {"title": "A", "variants": [{"price": 1000, "available": false}]}
        </script>
        """
        products = _extract_from_embedded_state(_soup(html), "https://example.com/p")
        assert products[0].in_stock is False


class TestExtractFromGenericHtml:
    def test_finds_product_card(self):
        html = """
        <div class="product-item"><h3>Widget</h3><span class="price">$9.99</span>
        <a href="/products/widget">link</a></div>
        """
        products = _extract_from_generic_html(_soup(html), "https://example.com/shop")
        assert len(products) == 1
        assert products[0].name == "Widget"
        assert products[0].price == Decimal("9.99")
        assert products[0].url == "https://example.com/products/widget"

    def test_container_without_heading_is_skipped(self):
        html = '<div class="product-item"><span class="price">$9.99</span></div>'
        assert _extract_from_generic_html(_soup(html), "https://example.com/shop") == []

    def test_container_without_product_class_is_ignored(self):
        html = '<div class="footer"><h3>Widget</h3><span class="price">$9.99</span></div>'
        assert _extract_from_generic_html(_soup(html), "https://example.com/shop") == []


class TestExtractProductsMerged:
    async def test_prefers_jsonld_over_llm_fallback(self):
        html = """
        <script type="application/ld+json">
        {"@type": "Product", "name": "Tulip", "offers": {"price": 10, "priceCurrency": "USD"}}
        </script>
        """
        fetched = FetchedPage(
            url="https://example.com/p", html=html, text="Tulip $10", next_page_url=None, fetched_via="http"
        )
        with patch("app.scraping.extractor._extract_products_llm_merged", new_callable=AsyncMock) as mock_llm:
            result = await extract_products_merged(fetched)
        mock_llm.assert_not_awaited()
        assert result.products[0].name == "Tulip"
        assert result.products[0].source == "jsonld"

    async def test_falls_back_to_llm_when_nothing_deterministic_found(self):
        fetched = FetchedPage(
            url="https://example.com/p",
            html="<div>no structured data here, just prose</div>",
            text="plain text",
            next_page_url=None,
            fetched_via="http",
        )
        with patch("app.scraping.extractor._extract_products_llm_merged", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = ExtractedProductList(products=[])
            await extract_products_merged(fetched)
        mock_llm.assert_awaited_once()

    async def test_falls_back_to_llm_when_html_is_empty(self):
        fetched = FetchedPage(
            url="https://example.com/p", html="", text="rendered by JS, only text available", next_page_url=None, fetched_via="browser"
        )
        with patch("app.scraping.extractor._extract_products_llm_merged", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = ExtractedProductList(products=[])
            await extract_products_merged(fetched)
        mock_llm.assert_awaited_once()
