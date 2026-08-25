"""Deterministic attribute parsing for hard-goods products (raised beds,
elevated planters, and their accessories) — turns a product's name/
description text into normalized comparison attributes when a site's
structured data (JSON-LD additionalProperty) doesn't already state them.

Deliberately regex/keyword-based, not an LLM call: this product category's
titles reliably state material and dimensions directly ("17-in Modular Metal
Raised Bed", "Cedar Raised Garden Bed 4x8"), so text parsing has good
coverage without the latency/cost/occasional-hallucination of an LLM pass —
and it keeps the comparison engine's claims fully auditable, per this
feature's whole point: explain deterministic analysis, don't invent it.
"""

import re

# Ordered longest-phrase-first so "galvanized steel" matches before a bare
# "steel" fallback would; canonical values are what the UI/matcher use.
_MATERIAL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bgalvani[sz]ed\s+steel\b", re.I), "galvanized_steel"),
    (re.compile(r"\bcorten\b|\bweathering\s+steel\b", re.I), "corten_steel"),
    (re.compile(r"\balu-?zinc\b", re.I), "aluzinc_steel"),
    (re.compile(r"\bstainless\s+steel\b", re.I), "stainless_steel"),
    (re.compile(r"\bcedar\b", re.I), "cedar"),
    (re.compile(r"\bredwood\b", re.I), "redwood"),
    (re.compile(r"\bpine\b", re.I), "pine"),
    (re.compile(r"\bfir\b", re.I), "fir"),
    (re.compile(r"\bcomposite\b", re.I), "composite"),
    (re.compile(r"\bpoly(propylene|ethylene)?\b|\bplastic\b", re.I), "plastic"),
    (re.compile(r"\bfabric\b|\bfelt\b|\bgrow\s*bag\b", re.I), "fabric"),
    (re.compile(r"\baluminum\b", re.I), "aluminum"),
    # Bare "steel"/"metal" last — only matches if none of the more specific
    # steel variants above already matched (checked in order in the caller).
    (re.compile(r"\bsteel\b", re.I), "steel"),
    (re.compile(r"\bmetal\b", re.I), "metal"),
    # Bare "wood"/"wooden" last of all — even less specific than "metal"; a
    # material-unspecified wood type still beats no material signal at all.
    (re.compile(r"\bwood(en)?\b", re.I), "wood"),
]

# (regex, product_type) — checked in order, first match wins. Accessories
# are listed before "raised_bed"/"elevated_planter" so a trellis or cover
# that happens to mention "bed" in its title (e.g. "Trellis for Raised Bed")
# doesn't get misclassified as the bed itself.
_PRODUCT_TYPE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\btrellis\b|\bcover\b|\bcloche\b|\bnetting\b|\birrigation\b|\bliner\b|\bcaster\b|\bwheel\s*kit\b", re.I), "accessory"),
    (re.compile(r"\belevated\s+planter\b|\braised\s+planter\b", re.I), "elevated_planter"),
    (re.compile(r"\braised\s+(garden\s+)?bed\b|\bgarden\s+bed\b", re.I), "raised_bed"),
    (re.compile(r"\bplanter\b", re.I), "elevated_planter"),
]

_FORM_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bmodular\b", re.I), "modular"),
    (re.compile(r"\brolling\b|\bwheel", re.I), "rolling"),
    (re.compile(r"\belevated\b|\bstanding\b|\blegs?\b", re.I), "elevated"),
]

# Height/depth stated in inches, e.g. `17"`, `17 in`, `17-inch`, `17in`.
# `\b` only guards the word-form ("in"/"inch") branch — a trailing quote
# mark is already an unambiguous terminator and, being a non-word
# character itself, `\b` would never match right after one anyway (no
# word/non-word transition when the string simply ends there).
_HEIGHT_INCHES_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(?:[\"'″]|-?\s*in(?:ch(?:es)?)?\b)", re.I)

# A number explicitly qualified as the height/depth dimension — checked
# before the bare _HEIGHT_INCHES_RE scan below, which otherwise has no way
# to tell a stated height apart from a footprint's length/width (a title
# like `34" x 68" (12" D)` states THREE dimensioned numbers; only "12" is
# the actual height, and it's only identifiable by the "D" that follows it).
_HEIGHT_QUALIFIED_RE = re.compile(
    r'(\d{1,3}(?:\.\d+)?)\s*(?:["\'″]|-?\s*in(?:ch(?:es)?)?)?\s*(?:tall|high|deep|d\))'
    r'|(?:tall|height|deep|depth)\D{0,8}?(\d{1,3}(?:\.\d+)?)\s*(?:["\'″]|-?\s*in(?:ch(?:es)?)?\b)',
    re.I,
)

# Configuration counts like "6-in-1", "9 in 1".
_CONFIGURATION_RE = re.compile(r"\b(\d{1,2})\s*-?\s*in\s*-?\s*1\b", re.I)

# Footprint dimensions like "2x8", "2' x 8'", `34" x 68"`. Captures each
# number's own unit mark (a mixed "2' x 96\"" is unlikely in practice, so
# either mark found is treated as the shared unit); bare numbers with no
# mark at all fall back to a size heuristic in _parse_footprint below.
_FOOTPRINT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(['\"]?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*(['\"]?)")


def _height_band(inches: float) -> str:
    if inches <= 12:
        return "shallow"
    if inches <= 20:
        return "standard"
    return "tall"


def _footprint_band(area_sqft: float) -> str:
    if area_sqft <= 8:
        return "small"
    if area_sqft <= 24:
        return "medium"
    return "large"


def _parse_footprint(match: re.Match) -> dict[str, str]:
    a, a_mark, b, b_mark = match.groups()
    length, width = float(a), float(b)
    mark = a_mark or b_mark
    if mark == "'":
        unit = "ft"
    elif mark == '"':
        unit = "in"
    else:
        # No unit stated at all — raised-bed footprints are conventionally
        # given in feet ("2x8", "4x4"); a bare number this large (e.g. a
        # "34x68" metal-bed footprint, which sites do state in inches even
        # unmarked) is the signal to assume inches instead.
        unit = "ft" if max(length, width) <= 12 else "in"
    length_in = length * 12 if unit == "ft" else length
    width_in = width * 12 if unit == "ft" else width
    # Reject implausible matches (stray SKU numbers, etc.) — raised beds/
    # planters realistically run roughly 6-150 inches (0.5-12.5ft) per side.
    if not (6 <= length_in <= 150 and 6 <= width_in <= 150):
        return {}
    area_sqft = (length_in * width_in) / 144
    return {
        "footprint": f"{a}x{b}{unit}",
        "footprint_sqft": f"{area_sqft:.1f}",
        "footprint_band": _footprint_band(area_sqft),
    }


def extract_attributes_from_text(name: str, description: str = "") -> dict[str, str]:
    """Best-effort attribute parse from product title + description text.

    Returns only keys it found real evidence for — never guesses a value
    just to fill a slot. Callers should treat this as a fallback, layered
    *under* any attributes already sourced from structured markup (see
    fill_missing_attributes below).
    """
    text = f"{name} {description}".strip()
    attributes: dict[str, str] = {}

    for pattern, material in _MATERIAL_PATTERNS:
        if pattern.search(text):
            attributes["material"] = material
            break

    for pattern, product_type in _PRODUCT_TYPE_PATTERNS:
        if pattern.search(text):
            attributes["product_type"] = product_type
            break

    for pattern, form in _FORM_PATTERNS:
        if pattern.search(text):
            attributes["form"] = form
            break
    else:
        # No explicit form language found — a raised bed with no stated
        # form is conventionally ground-level, but only assert that for
        # the product types where "form" is a meaningful distinction.
        if attributes.get("product_type") in ("raised_bed", "elevated_planter"):
            attributes["form"] = "ground"

    # A footprint match (length x width) is found first so an unqualified
    # height scan can skip over its span below — otherwise a title like
    # `34" x 68" (12" D)` would misread the *length* as the height, since
    # it's simply the first quoted number in the text.
    footprint_match = _FOOTPRINT_RE.search(text)
    if footprint_match:
        attributes.update(_parse_footprint(footprint_match))

    qualified_height = _HEIGHT_QUALIFIED_RE.search(text)
    if qualified_height:
        inches = float(next(g for g in qualified_height.groups() if g))
    else:
        search_text = text
        if footprint_match:
            start, end = footprint_match.span()
            search_text = text[:start] + " " * (end - start) + text[end:]
        unqualified_height = _HEIGHT_INCHES_RE.search(search_text)
        inches = float(unqualified_height.group(1)) if unqualified_height else None

    if inches is not None:
        # Reject implausible matches (stray SKU numbers, etc.) — raised
        # beds/planters realistically run roughly 4-42 inches tall.
        if 4 <= inches <= 42:
            attributes["height_in"] = str(inches)
            attributes["height_band"] = _height_band(inches)

    config_match = _CONFIGURATION_RE.search(text)
    if config_match:
        attributes["configuration"] = f"{config_match.group(1)}-in-1"

    return attributes


def fill_missing_attributes(existing: dict[str, str], name: str, description: str = "") -> dict[str, str]:
    """Layers text-parsed attributes under whatever's already known
    (e.g. from JSON-LD additionalProperty, a stronger signal when present)
    — never overwrites a real value, only fills genuine gaps.
    """
    parsed = extract_attributes_from_text(name, description)
    merged = dict(existing)
    for key, value in parsed.items():
        if not merged.get(key):
            merged[key] = value
    return merged
