"""Tests for the pure/deterministic parts of app/scraping/discovery.py:
URL normalization, domain restriction, path-based classification, and
sitemap XML parsing (network calls mocked via httpx.MockTransport rather
than hitting a real site).
"""

import httpx

from app.scraping.discovery import (
    _parse_sitemap,
    classify_url_by_page_signals,
    classify_url_by_path,
    extract_product_links,
    is_same_site,
    normalize_url,
)


class TestNormalizeUrl:
    def test_strips_fragment(self):
        assert normalize_url("https://example.com/page#section") == "https://example.com/page"

    def test_strips_tracking_params(self):
        assert normalize_url("https://example.com/page?utm_source=newsletter&id=5") == "https://example.com/page?id=5"

    def test_strips_trailing_slash(self):
        assert normalize_url("https://example.com/page/") == "https://example.com/page"

    def test_keeps_bare_root_slash(self):
        assert normalize_url("https://example.com/") == "https://example.com/"

    def test_sorts_query_params_for_stable_dedup(self):
        assert normalize_url("https://example.com/p?b=2&a=1") == normalize_url("https://example.com/p?a=1&b=2")

    def test_resolves_relative_url_against_base(self):
        assert normalize_url("/products/x", base_url="https://example.com/y") == "https://example.com/products/x"

    def test_drops_multiple_tracking_params(self):
        url = "https://example.com/p?fbclid=1&gclid=2&id=5&mc_cid=3"
        assert normalize_url(url) == "https://example.com/p?id=5"


class TestIsSameSite:
    def test_same_domain(self):
        assert is_same_site("https://example.com/a", "https://example.com/b")

    def test_www_prefix_is_ignored(self):
        assert is_same_site("https://www.example.com/a", "https://example.com/b")

    def test_different_domain_is_rejected(self):
        assert not is_same_site("https://other.com/a", "https://example.com/b")

    def test_subdomain_is_rejected(self):
        assert not is_same_site("https://shop.example.com/a", "https://example.com/b")


class TestClassifyUrlByPath:
    def test_product_path(self):
        assert classify_url_by_path("https://example.com/products/tulip-bulb") == "product"

    def test_category_path(self):
        assert classify_url_by_path("https://example.com/collections/perennials") == "category"

    def test_promotional_path(self):
        assert classify_url_by_path("https://example.com/sale") == "promotional"

    def test_unclassifiable_path_is_unknown(self):
        assert classify_url_by_path("https://example.com/about-us") == "unknown"


class TestExtractProductLinks:
    def test_finds_product_links_on_a_category_page(self):
        html = """
        <a href="/products/tulip-bulb">Tulip</a>
        <a href="/products/daffodil-bulb">Daffodil</a>
        <a href="/collections/bulbs">All bulbs</a>
        <a href="/about-us">About</a>
        """
        links = extract_product_links(html, "https://example.com/collections/perennials", "https://example.com")
        assert links == {
            "https://example.com/products/tulip-bulb",
            "https://example.com/products/daffodil-bulb",
        }

    def test_ignores_links_to_other_domains(self):
        html = '<a href="https://other-site.com/products/tulip-bulb">Tulip</a>'
        links = extract_product_links(html, "https://example.com/collections/perennials", "https://example.com")
        assert links == set()

    def test_no_product_links_returns_empty_set(self):
        html = '<a href="/collections/bulbs">All bulbs</a>'
        links = extract_product_links(html, "https://example.com/collections/perennials", "https://example.com")
        assert links == set()

    def test_falls_back_to_nested_path_depth_when_no_naming_convention_matches(self):
        """Sites without a /products/ URL convention (e.g. Holland Bulb
        Farms' deep taxonomy paths) don't match classify_url_by_path at
        all — a link nested deeper under the category page's own path is
        still treated as a product candidate."""
        html = """
        <a href="/spring-planting-bulbs/perennials/hosta/first-frost-hosta">First Frost Hosta</a>
        <a href="/spring-planting-bulbs/perennials">Back to category</a>
        <a href="/spring-planting-bulbs/dahlias">A different category</a>
        """
        links = extract_product_links(
            html, "https://example.com/spring-planting-bulbs/perennials", "https://example.com"
        )
        assert links == {"https://example.com/spring-planting-bulbs/perennials/hosta/first-frost-hosta"}


class TestClassifyUrlByPageSignals:
    async def test_detects_product_via_jsonld(self):
        def handler(request):
            html = '<script type="application/ld+json">{"@type": "Product", "name": "Tulip"}</script>'
            return httpx.Response(200, text=html)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await classify_url_by_page_signals(client, "https://example.com/x") == "product"

    async def test_detects_promo_via_banner_element(self):
        def handler(request):
            html = '<div class="announcement-bar">Big sale! 20% off everything</div>'
            return httpx.Response(200, text=html)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await classify_url_by_page_signals(client, "https://example.com/x") == "promotional"

    async def test_nav_menu_mentioning_a_sale_category_is_not_promotional(self):
        """Regression test: a nav menu link literally titled "Clearance"
        (a real product category, not a promo banner) must not make every
        page on the site classify as promotional — the earlier whole-page
        text scan did exactly that on a real competitor site."""

        def handler(request):
            html = '<nav class="site-nav"><a href="/clearance">Clearance</a></nav><p>A perfectly ordinary page.</p>'
            return httpx.Response(200, text=html)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await classify_url_by_page_signals(client, "https://example.com/x") == "unknown"

    async def test_detects_product_via_microdata(self):
        def handler(request):
            html = (
                '<div itemscope itemtype="http://schema.org/Product">'
                '<span itemprop="name">Tulip</span></div>'
            )
            return httpx.Response(200, text=html)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await classify_url_by_page_signals(client, "https://example.com/x") == "product"

    async def test_detects_product_via_og_type(self):
        def handler(request):
            html = '<meta property="og:type" content="product">'
            return httpx.Response(200, text=html)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await classify_url_by_page_signals(client, "https://example.com/x") == "product"

    async def test_unknown_when_neither_signal_present(self):
        def handler(request):
            return httpx.Response(200, text="Just a plain informational page.")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await classify_url_by_page_signals(client, "https://example.com/x") == "unknown"

    async def test_unknown_on_error_status(self):
        def handler(request):
            return httpx.Response(404, text="not found")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await classify_url_by_page_signals(client, "https://example.com/x") == "unknown"


class TestParseSitemap:
    async def test_flat_urlset(self):
        xml = (
            '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            "<url><loc>https://example.com/a</loc></url>"
            "<url><loc>https://example.com/b</loc></url>"
            "</urlset>"
        )

        def handler(request):
            return httpx.Response(200, text=xml)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            urls = await _parse_sitemap(client, "https://example.com/sitemap.xml", 0)
        assert urls == ["https://example.com/a", "https://example.com/b"]

    async def test_sitemapindex_recurses_into_leaf_sitemaps(self):
        index_xml = (
            '<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            "<sitemap><loc>https://example.com/sitemap-products.xml</loc></sitemap>"
            "</sitemapindex>"
        )
        leaf_xml = (
            '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            "<url><loc>https://example.com/products/tulip</loc></url>"
            "</urlset>"
        )

        def handler(request):
            if "sitemap-products" in str(request.url):
                return httpx.Response(200, text=leaf_xml)
            return httpx.Response(200, text=index_xml)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            urls = await _parse_sitemap(client, "https://example.com/sitemap.xml", 0)
        assert urls == ["https://example.com/products/tulip"]

    async def test_malformed_xml_returns_empty_not_raises(self):
        def handler(request):
            return httpx.Response(200, text="not xml at all <<<")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await _parse_sitemap(client, "https://example.com/sitemap.xml", 0) == []

    async def test_error_status_returns_empty(self):
        def handler(request):
            return httpx.Response(500, text="server error")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await _parse_sitemap(client, "https://example.com/sitemap.xml", 0) == []
