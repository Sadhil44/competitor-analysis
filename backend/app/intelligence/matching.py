"""Attribute-based product-comparison scoring — replaces loose name-only
matching with an explainable score built from the normalized attributes in
Product.attributes (see app/intelligence/normalizer.py).

Deliberately a plain Python module, not a SQL query: the per-competitor
candidate set for one product_type is small (dozens, not thousands), so
scoring in Python is fine, and it's the only way to get an inspectable
per-field score breakdown back to the caller (a single fused SQL query, the
existing app/api/products.py::_search_by_keywords pattern, couldn't return
"matched on material and height, missing form" the way this does).
"""

from dataclasses import dataclass, field
from difflib import SequenceMatcher

# Weights per the PRD's own comparison-engine spec — material is the
# single biggest signal, name similarity is a tie-breaker only, never the
# primary matcher (checked last, contributes least).
_FIELD_WEIGHTS: dict[str, int] = {
    "material": 30,
    "height_band": 20,
    "footprint_band": 20,
    "form": 15,
    "configuration": 10,
}
_NAME_SIMILARITY_WEIGHT = 5
MAX_SCORE = sum(_FIELD_WEIGHTS.values()) + _NAME_SIMILARITY_WEIGHT  # 100


@dataclass
class MatchResult:
    product_id: int
    score: int  # 0-100, see MAX_SCORE
    matched_fields: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    confidence: str = "low"  # "high" | "medium" | "low"


def _confidence(score: int) -> str:
    # Thresholds chosen so a bare product_type match with nothing else
    # (score from name similarity alone, <=5) reads as "low" — comparable
    # products only earn "high" by agreeing on material AND at least one
    # dimension signal (30 + 20 = 50, plus name similarity, clears 65).
    if score >= 65:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def score_pair(
    target_attrs: dict[str, str],
    candidate_attrs: dict[str, str],
    target_name: str,
    candidate_name: str,
) -> MatchResult:
    """Scores how comparable `candidate` is to `target` — callers gate on
    product_type equality themselves (see find_comparables) since that's a
    hard filter, not a scored field: a trellis should never even reach this
    function when comparing raised beds.
    """
    matched: list[str] = []
    missing: list[str] = []
    score = 0

    for attr_key, weight in _FIELD_WEIGHTS.items():
        target_value = target_attrs.get(attr_key)
        candidate_value = candidate_attrs.get(attr_key)
        if not target_value or not candidate_value:
            missing.append(attr_key)
        elif target_value == candidate_value:
            matched.append(attr_key)
            score += weight
        # Both present but disagree (e.g. cedar vs. metal) scores zero for
        # this field and isn't "missing" — it's a real, informative
        # mismatch, distinct from "we just don't know."

    name_similarity = SequenceMatcher(None, target_name.lower(), candidate_name.lower()).ratio()
    score += round(name_similarity * _NAME_SIMILARITY_WEIGHT)

    return MatchResult(
        product_id=0,  # caller fills this in (see find_comparables)
        score=score,
        matched_fields=matched,
        missing_fields=missing,
        confidence=_confidence(score),
    )


def find_comparables(
    target_id: int,
    target_attrs: dict[str, str],
    target_name: str,
    candidates: list[tuple[int, dict[str, str], str]],
    *,
    limit: int = 10,
) -> list[MatchResult]:
    """Scores every candidate against the target and returns the top
    matches, best first. `candidates` is a list of (product_id, attributes,
    name) tuples — typically every other in-scope product regardless of
    product_type; the caller doesn't need to pre-filter, since this
    function enforces the product_type gate itself (a trellis must never
    outrank a genuinely comparable bed just because a caller forgot to
    filter first — this is the one rule the PRD treats as non-negotiable).

    A product with no recorded product_type at all is excluded from
    matching entirely (as both target and candidate) — "unknown" is not
    the same as "same type," and letting it through would silently start
    matching un-classified products against everything.
    """
    target_type = target_attrs.get("product_type")
    if not target_type:
        return []

    results = []
    for candidate_id, candidate_attrs, candidate_name in candidates:
        if candidate_id == target_id:
            continue
        if candidate_attrs.get("product_type") != target_type:
            continue
        result = score_pair(target_attrs, candidate_attrs, target_name, candidate_name)
        result.product_id = candidate_id
        results.append(result)
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:limit]
