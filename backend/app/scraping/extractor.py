from anthropic import AsyncAnthropic

from app.schemas.extraction import ExtractedProductList

client = AsyncAnthropic()

EXTRACTION_MODEL = "claude-haiku-4-5"


async def extract_products(page_text: str) -> ExtractedProductList:
    """Turn scraped page text into structured product/price data.

    Uses Claude's native structured-output support (client.messages.parse)
    rather than a separate library — the response is validated against
    ExtractedProductList automatically. Haiku tier: this runs once per page
    per crawl, potentially many times, so cost matters more here than for
    the agent's own reasoning (which uses a stronger model in Phase 3).
    """
    # The SDK refuses a non-streaming call whose max_tokens ceiling makes it
    # *estimate* the request could exceed 10 minutes — a conservative,
    # ceiling-based heuristic, not a reflection of actual usage (these calls
    # finish in seconds). Extending the client timeout suppresses that guard
    # without needing to restructure this as a streaming call.
    response = await client.with_options(timeout=600.0).messages.parse(
        model=EXTRACTION_MODEL,
        # 4096 truncated mid-JSON on a real catalog page; 16000 still
        # under-extracted on a single long page with ~140 products (the
        # model satisficed rather than running out of room) — 32000 gives
        # real headroom (Haiku 4.5 supports up to 64K output).
        max_tokens=32000,
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract EVERY product listed on this page — do not skip any, "
                    "even if there are 100+ products. Some pages list a large "
                    "number of items; be exhaustive, not selective.\n\n"
                    "For each product, extract: name, price, currency, stock status, "
                    "and sku if a SKU or item number is shown (e.g. 'SKU: 12345') — "
                    "leave sku null only if none is visible.\n\n"
                    "Some listings show a current/sale price alongside a crossed-out "
                    "original price (e.g. '$17.98 Was: $44.95') — extract the "
                    "current/sale price ($17.98), not the original.\n\n"
                    "Page content:\n\n" + page_text
                ),
            }
        ],
        output_format=ExtractedProductList,
    )
    return response.parsed_output
