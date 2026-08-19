"""Deterministic-first promotional/campaign detection.

Scans banner/announcement-shaped elements (the common home for sitewide
sale messaging — announcement bars, hero banners, top bars) for discount
language. When the discount is stated in a regex-parseable form ("20%
off", "$10 off", "code SAVE20") a DetectedCampaign is built directly from
the match — no LLM involved. Banner text that clearly signals a promotion
but isn't in a parseable form (e.g. "Big End of Summer Savings — This
Weekend Only") falls back to a bounded LLM normalization pass whose only
job is to phrase what's already there, not to decide whether a promo
exists (that's already been confirmed deterministically).
"""

import asyncio
import logging
import re

from anthropic import AsyncAnthropic
from bs4 import BeautifulSoup
from pydantic import BaseModel

from app.schemas.campaign import DetectedCampaign

logger = logging.getLogger(__name__)

client = AsyncAnthropic()

NORMALIZATION_MODEL = "claude-haiku-4-5"

_BANNER_HINTS = re.compile(r"announce|banner|promo|hero|marquee|top-?bar", re.IGNORECASE)
_DISCOUNT_SIGNAL = re.compile(
    r"%\s?off|\$\d+(?:\.\d{2})?\s?off|buy one get one|\bbogo\b|free shipping|"
    r"clearance|\bsale\b|coupon|promo code|use code",
    re.IGNORECASE,
)
_PERCENT_OFF = re.compile(r"\b(\d{1,3})\s?%\s?off\b", re.IGNORECASE)
_DOLLAR_OFF = re.compile(r"\$(\d+(?:\.\d{2})?)\s?off\b", re.IGNORECASE)
_COUPON_CODE = re.compile(r"(?:code|coupon)[:\s]+([A-Z0-9]{3,20})\b")

MAX_BANNER_TEXT_LENGTH = 300
MAX_CANDIDATES_PER_PAGE = 5


def _clean_text(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split())


def _build_discount_text(text: str) -> str:
    parts = []
    percent = _PERCENT_OFF.search(text)
    if percent:
        parts.append(f"{percent.group(1)}% off")
    dollar = _DOLLAR_OFF.search(text)
    if dollar:
        parts.append(f"${dollar.group(1)} off")
    coupon = _COUPON_CODE.search(text)
    if coupon:
        parts.append(f"code {coupon.group(1)}")
    return "; ".join(parts)


def _find_candidate_texts(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates = soup.find_all(
        lambda tag: tag.name in ("div", "section", "aside", "p", "a")
        and (
            any(_BANNER_HINTS.search(c) for c in tag.get("class", []))
            or _BANNER_HINTS.search(tag.get("id", "") or "")
        )
    )
    texts: list[str] = []
    seen: set[str] = set()
    for el in candidates:
        text = _clean_text(el)[:MAX_BANNER_TEXT_LENGTH]
        if text and text not in seen and _DISCOUNT_SIGNAL.search(text):
            seen.add(text)
            texts.append(text)
        if len(texts) >= MAX_CANDIDATES_PER_PAGE:
            break
    return texts


def detect_campaigns_deterministic(html: str, page_url: str) -> tuple[list[DetectedCampaign], list[str]]:
    """Returns (confidently parsed campaigns, ambiguous banner texts that
    still need LLM normalization)."""
    confident: list[DetectedCampaign] = []
    ambiguous: list[str] = []
    for text in _find_candidate_texts(html):
        discount_text = _build_discount_text(text)
        if discount_text:
            confident.append(
                DetectedCampaign(title=text[:80], description=text, discount_text=discount_text, source_url=page_url)
            )
        else:
            ambiguous.append(text)
    return confident, ambiguous


class _NormalizedCampaignText(BaseModel):
    title: str
    description: str
    discount_text: str


async def _normalize_with_llm(text: str, page_url: str) -> DetectedCampaign | None:
    try:
        response = await client.messages.parse(
            model=NORMALIZATION_MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "This text is from a promotional banner on an ecommerce site. "
                        "Produce a short title, a one-sentence description, and a short "
                        "discount_text summarizing the offer (e.g. '20% off', 'BOGO', "
                        "'$10 off orders over $50'). If the text states no concrete "
                        "discount (just mood/branding with no actual offer), set "
                        "discount_text to an empty string. Do not invent an amount, "
                        "code, or date that isn't stated in the text.\n\n"
                        f"Banner text: {text}"
                    ),
                }
            ],
            output_format=_NormalizedCampaignText,
        )
    except Exception:
        logger.warning("campaign LLM normalization failed for url=%s", page_url, exc_info=True)
        return None

    parsed = response.parsed_output
    if not parsed.discount_text:
        return None
    return DetectedCampaign(
        title=parsed.title, description=parsed.description, discount_text=parsed.discount_text, source_url=page_url
    )


async def discover_campaigns(html: str, page_url: str) -> list[DetectedCampaign]:
    """Top-level entry point: deterministic banner scan first, LLM
    normalization only for whatever it flagged as promotional but
    couldn't cleanly parse.
    """
    confident, ambiguous = detect_campaigns_deterministic(html, page_url)
    if not ambiguous:
        return confident

    normalized = await asyncio.gather(*[_normalize_with_llm(text, page_url) for text in ambiguous])
    confident.extend(c for c in normalized if c is not None)
    logger.info(
        "campaign discovery url=%s deterministic=%d llm_normalized=%d",
        page_url,
        len(confident) - sum(1 for c in normalized if c is not None),
        sum(1 for c in normalized if c is not None),
    )
    return confident
