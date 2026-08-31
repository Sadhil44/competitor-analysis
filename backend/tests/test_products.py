"""Tests for the cross-competitor product search endpoint
(GET /products/search) — the shared full-text-search core it uses
(_search_by_keywords) also backs /products/{id}/comparable.

Runs against the same real dev DB every other test does (see
tests/conftest.py) — there's real product data in it, so assertions use
distinctive nonsense tokens unlikely to collide with anything real, and
check for containment rather than exact-set equality.
"""

from app.models import Product


async def _make_product(db_session, competitor_factory, name: str) -> Product:
    competitor = await competitor_factory()
    product = Product(competitor_id=competitor.id, name=name, url="")
    db_session.add(product)
    await db_session.flush()
    await db_session.commit()
    return product


async def test_matches_products_across_different_competitors(client, db_session, competitor_factory):
    # Keywords are OR'd together (see _search_by_keywords), so a real word
    # like "tulip" alone would also match plenty of real, pre-existing
    # products in this shared dev DB — search on the nonsense token alone
    # to keep this deterministic, and check containment (both of ours
    # appear, ranked among whatever else "blorptastic" happens to match —
    # nothing else, realistically) rather than exact-set equality.
    p1 = await _make_product(db_session, competitor_factory, "Zzyxquil Blorptastic Hybrid Tulip")
    p2 = await _make_product(db_session, competitor_factory, "Van Eijk Zzyxquil Blorptastic Tulip")

    response = await client.get("/products/search", params={"q": "blorptastic", "limit": 50})
    assert response.status_code == 200
    ids = {row["id"] for row in response.json()}
    assert {p1.id, p2.id} <= ids


async def test_unrelated_products_are_not_matched(client, db_session, competitor_factory):
    product = await _make_product(db_session, competitor_factory, "Zzyxquil Blorptastic Hybrid Tulip")

    response = await client.get("/products/search", params={"q": "flibbertigibbet wallaby"})
    assert response.status_code == 200
    assert product.id not in {row["id"] for row in response.json()}


async def test_blank_query_returns_empty_list_not_every_product(client, db_session, competitor_factory):
    await _make_product(db_session, competitor_factory, "Zzyxquil Blorptastic Hybrid Tulip")

    response = await client.get("/products/search", params={"q": "   "})
    assert response.status_code == 200
    assert response.json() == []


async def test_respects_limit(client, db_session, competitor_factory):
    for i in range(5):
        await _make_product(db_session, competitor_factory, f"Zzyxquil Blorptastic Variant {i}")

    response = await client.get("/products/search", params={"q": "zzyxquil blorptastic", "limit": 2})
    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_compound_query_falls_back_to_substring_match(client, db_session, competitor_factory):
    # "zzyxworkbench" is a single nonsense token — to_tsquery finds nothing
    # for it (no product is literally named that), which is exactly when
    # _fallback_keyword_scan (name_matches_query) should kick in and catch
    # a real product whose own word ("bench") is a substring of it.
    product = await _make_product(db_session, competitor_factory, "Cedar Zzyxworkbench Storage Bench")

    response = await client.get("/products/search", params={"q": "zzyxworkbench"})
    assert response.status_code == 200
    assert product.id in {row["id"] for row in response.json()}


async def test_fallback_ignores_short_incidental_substrings(client, db_session, competitor_factory):
    # "ben" is a coincidental 3-letter substring of "zzyxworkbench" (the
    # tail end of "...bench") with no real relation to it — the fallback's
    # length-4 floor on name words exists specifically to keep this from
    # matching (see app/intelligence/text.py's name_matches_query). The
    # product name deliberately does NOT contain "zzyxworkbench" itself, so
    # the only possible match path is the word-level "ben" substring check.
    product = await _make_product(db_session, competitor_factory, "Zzyxlark Ben Rack")

    response = await client.get("/products/search", params={"q": "zzyxworkbench"})
    assert response.status_code == 200
    assert product.id not in {row["id"] for row in response.json()}
