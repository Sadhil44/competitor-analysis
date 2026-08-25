"""Unit tests for app/intelligence/matching.py — pure functions, no DB
fixtures needed. Fixture attribute dicts are written in the shape
app/intelligence/normalizer.py actually produces, not idealized data, so
these tests exercise the same "some fields missing" reality real crawled
products have.
"""

from app.intelligence.matching import find_comparables, score_pair

# Five curated products across three brands, all genuinely comparable
# raised beds/planters with varying attribute completeness.
CEDAR_BED_A = (1, {"product_type": "raised_bed", "material": "cedar", "height_band": "shallow", "form": "ground"}, "Farmstead Cedar Raised Garden Bed, 2'")
CEDAR_BED_B = (2, {"product_type": "raised_bed", "material": "cedar", "height_band": "shallow", "form": "ground"}, "2' Cedar Raised Bed Garden Bed")
METAL_MODULAR_A = (3, {"product_type": "raised_bed", "material": "metal", "height_band": "standard", "form": "modular", "configuration": "9-in-1"}, "17-in Tall 9 In 1 Modular Metal Raised Garden Bed")
METAL_MODULAR_B = (4, {"product_type": "raised_bed", "material": "aluzinc_steel", "height_band": "standard", "form": "modular"}, "Medium Modular Metal Raised Garden Bed - 15in Tall")
ELEVATED_PLANTER = (5, {"product_type": "elevated_planter", "material": "composite", "form": "elevated"}, "Composite Elevated Planter Box")

# Five products that should NOT be treated as comparable to a raised bed.
ACCESSORY_TRELLIS = (6, {"product_type": "accessory", "material": "metal"}, "Trellis for Raised Bed")
ACCESSORY_COVER = (7, {"product_type": "accessory"}, "Raised Bed Cover")
GIFT_CARD = (8, {}, "Epic Gardening Gift Card")
DIFFERENT_MATERIAL_BED = (9, {"product_type": "raised_bed", "material": "plastic", "height_band": "tall", "form": "rolling"}, "Rolling Plastic Planter Cart")
UNKNOWN_TYPE_PRODUCT = (10, {"material": "cedar"}, "Cedar Something")


def test_same_material_height_and_form_scores_high_confidence():
    result = score_pair(CEDAR_BED_A[1], CEDAR_BED_B[1], CEDAR_BED_A[2], CEDAR_BED_B[2])
    assert result.confidence == "high"
    assert "material" in result.matched_fields
    assert "height_band" in result.matched_fields
    assert "form" in result.matched_fields


def test_material_and_form_match_despite_missing_height_on_one_side():
    # METAL_MODULAR_B has no configuration recorded at all — missing, not
    # a mismatch — and its material ("aluzinc_steel") differs from A's
    # plain "metal", so material should NOT count as matched here.
    result = score_pair(METAL_MODULAR_A[1], METAL_MODULAR_B[1], METAL_MODULAR_A[2], METAL_MODULAR_B[2])
    assert "material" not in result.matched_fields
    assert "form" in result.matched_fields
    assert "height_band" in result.matched_fields
    assert "configuration" in result.missing_fields


def test_disagreeing_material_is_a_real_mismatch_not_missing():
    result = score_pair(CEDAR_BED_A[1], DIFFERENT_MATERIAL_BED[1], CEDAR_BED_A[2], DIFFERENT_MATERIAL_BED[2])
    assert "material" not in result.matched_fields
    assert "material" not in result.missing_fields  # both sides had a value; they just disagreed


def test_completely_unknown_attributes_still_scores_via_name_only():
    result = score_pair({"product_type": "raised_bed"}, {"product_type": "raised_bed"}, "Cedar Raised Bed", "Metal Raised Bed")
    assert result.confidence == "low"
    assert result.score <= 5


def test_find_comparables_never_matches_accessory_to_raised_bed():
    target_id, target_attrs, target_name = CEDAR_BED_A
    candidates = [ACCESSORY_TRELLIS, ACCESSORY_COVER, CEDAR_BED_B, METAL_MODULAR_A]
    results = find_comparables(target_id, target_attrs, target_name, candidates)
    matched_ids = {r.product_id for r in results}
    assert ACCESSORY_TRELLIS[0] not in matched_ids
    assert ACCESSORY_COVER[0] not in matched_ids


def test_find_comparables_excludes_products_with_no_product_type_at_all():
    target_id, target_attrs, target_name = CEDAR_BED_A
    candidates = [GIFT_CARD, UNKNOWN_TYPE_PRODUCT, CEDAR_BED_B]
    results = find_comparables(target_id, target_attrs, target_name, candidates)
    matched_ids = {r.product_id for r in results}
    assert GIFT_CARD[0] not in matched_ids
    assert UNKNOWN_TYPE_PRODUCT[0] not in matched_ids
    assert CEDAR_BED_B[0] in matched_ids


def test_find_comparables_excludes_different_product_type():
    target_id, target_attrs, target_name = CEDAR_BED_A
    candidates = [ELEVATED_PLANTER, CEDAR_BED_B]
    results = find_comparables(target_id, target_attrs, target_name, candidates)
    matched_ids = {r.product_id for r in results}
    assert ELEVATED_PLANTER[0] not in matched_ids
    assert CEDAR_BED_B[0] in matched_ids


def test_find_comparables_excludes_target_itself():
    target_id, target_attrs, target_name = CEDAR_BED_A
    candidates = [CEDAR_BED_A, CEDAR_BED_B]
    results = find_comparables(target_id, target_attrs, target_name, candidates)
    matched_ids = {r.product_id for r in results}
    assert CEDAR_BED_A[0] not in matched_ids


def test_find_comparables_with_no_product_type_on_target_returns_nothing():
    results = find_comparables(99, {"material": "cedar"}, "Mystery Product", [CEDAR_BED_A, CEDAR_BED_B])
    assert results == []


def test_find_comparables_ranks_best_match_first():
    target_id, target_attrs, target_name = METAL_MODULAR_A
    candidates = [METAL_MODULAR_B, DIFFERENT_MATERIAL_BED]
    results = find_comparables(target_id, target_attrs, target_name, candidates)
    assert results[0].product_id == METAL_MODULAR_B[0]


def test_find_comparables_respects_limit():
    target_id, target_attrs, target_name = CEDAR_BED_A
    many_candidates = [(100 + i, CEDAR_BED_B[1], f"Cedar Bed Variant {i}") for i in range(20)]
    results = find_comparables(target_id, target_attrs, target_name, many_candidates, limit=3)
    assert len(results) == 3
