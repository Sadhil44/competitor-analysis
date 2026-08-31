"""Shared keyword extraction for product-name matching — used by both the
cross-competitor search endpoint (app/api/products.py) and the agent's
query_price_history/search_campaigns tools (app/agent/tools/__init__.py).

Moved here from app/api/products.py: those two tools used to do a literal
`Product.name.ilike(f"%{product_query}%")` substring match, which silently
returns nothing for a real, in-scope query like "workbench" when the
recorded products are actually named "Potting Bench"/"Cedar Bench Kit" —
same failure mode _find_competitor was fixed for earlier (a vocabulary
near-miss reading as "no data exists" instead of "my search term was too
narrow"). Keyword-OR matching (or full to_tsvector search, see
_search_by_keywords) fixes both call sites at once by sharing this.
"""

import re

_STOPWORDS = {"the", "and", "of", "for", "with", "our", "your", "in", "on", "is", "are"}


def significant_keywords(name: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9]+", name.lower())
    return [w for w in words if len(w) > 2 and w not in _STOPWORDS]


def name_matches_query(product_name: str, query_keywords: list[str]) -> bool:
    """True if `product_name` is a plausible match for a search built from
    `query_keywords` — bidirectional substring overlap, not just "keyword is
    a substring of the name" (significant_keywords + plain ilike still
    misses "workbench" (query) vs. "Cedar Potting Bench" (real product
    name): neither is a substring of the other as whole strings, but the
    name's own word "bench" IS a substring of the query word "workbench".
    Checking both directions, word-by-word, catches that without needing
    stemming or a synonym list.
    """
    if not query_keywords:
        return True
    name_lower = product_name.lower()
    # A higher length floor than significant_keywords()'s (>2) specifically
    # for the reverse "name word is a substring of the query word" check
    # below — a 3-letter name word like "ben" or "was" is a coincidental
    # substring of all sorts of unrelated compound words (e.g. "ben" inside
    # "workBENch"), producing false-positive matches with no real relation
    # to the query. 4+ letters is enough to keep genuine cases like "bench"
    # matching a "workbench" query.
    name_words = [w for w in re.findall(r"[a-zA-Z0-9]+", name_lower) if len(w) >= 4]
    for kw in query_keywords:
        if kw in name_lower:
            return True
        for word in name_words:
            if kw in word or word in kw:
                return True
    return False
