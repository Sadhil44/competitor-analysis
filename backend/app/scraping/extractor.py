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
    response = await client.messages.parse(
        model=EXTRACTION_MODEL,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract every product listed on this page, with its price, "
                    "currency, and stock status:\n\n" + page_text
                ),
            }
        ],
        output_format=ExtractedProductList,
    )
    return response.parsed_output
