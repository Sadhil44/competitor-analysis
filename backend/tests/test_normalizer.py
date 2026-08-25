"""Unit tests for app/intelligence/normalizer.py's deterministic text
parsing — pure functions, no DB fixtures needed.
"""

from app.intelligence.normalizer import extract_attributes_from_text, fill_missing_attributes


def test_parses_material_height_and_configuration_from_title():
    attrs = extract_attributes_from_text("Vego Garden 24-in Tall 6-in-1 Modular Metal Raised Bed")
    assert attrs["material"] == "metal"
    assert attrs["height_in"] == "24.0"
    assert attrs["height_band"] == "tall"
    assert attrs["configuration"] == "6-in-1"
    assert attrs["product_type"] == "raised_bed"
    assert attrs["form"] == "modular"


def test_more_specific_material_wins_over_generic_steel():
    attrs = extract_attributes_from_text("Birdies Galvanized Steel Raised Garden Bed")
    assert attrs["material"] == "galvanized_steel"


def test_shallow_height_band():
    attrs = extract_attributes_from_text('Cedar Raised Garden Bed 8"')
    assert attrs["height_band"] == "shallow"


def test_accessory_not_classified_as_raised_bed():
    attrs = extract_attributes_from_text("Trellis for Raised Bed")
    assert attrs["product_type"] == "accessory"


def test_no_material_language_leaves_material_unset():
    attrs = extract_attributes_from_text("Deluxe Garden Kit")
    assert "material" not in attrs


def test_implausible_height_number_is_rejected():
    # A "4x8" footprint dimension shouldn't be misread as a 4-inch height.
    attrs = extract_attributes_from_text("Cedar Raised Bed 4x8 Footprint")
    assert attrs.get("height_in") != "4.0"


def test_fill_missing_attributes_never_overwrites_existing_values():
    existing = {"material": "cedar"}
    merged = fill_missing_attributes(existing, "Galvanized Steel Raised Bed")
    assert merged["material"] == "cedar"


def test_fill_missing_attributes_fills_genuine_gaps():
    existing = {"material": "cedar"}
    merged = fill_missing_attributes(existing, 'Cedar Raised Bed 12"')
    assert merged["material"] == "cedar"
    assert merged["height_band"] == "shallow"


def test_footprint_parses_length_width_area_and_band():
    attrs = extract_attributes_from_text("Pine Raised Bed 2' x 8'")
    assert attrs["footprint"] == "2x8ft"
    assert attrs["footprint_sqft"] == "16.0"
    assert attrs["footprint_band"] == "medium"


def test_bare_footprint_dimensions_assumed_feet_when_small():
    attrs = extract_attributes_from_text("Corten Steel Modular Raised Bed 2x6")
    assert attrs["footprint"] == "2x6ft"


def test_depth_qualified_by_d_wins_over_footprint_length_as_height():
    # Regression: the length ("34") used to get misread as height just for
    # being the first quoted number — only "12" is actually the height here.
    attrs = extract_attributes_from_text('Demeter Corrugated Metal Raised Bed, 34" x 68" (12" D)')
    assert attrs["height_in"] == "12.0"
    assert attrs["height_band"] == "shallow"
    assert attrs["footprint"] == "34x68in"


def test_tall_keyword_after_number_still_wins_over_footprint():
    attrs = extract_attributes_from_text("17-in Tall Modular Bed 2x8")
    assert attrs["height_in"] == "17.0"


def test_wood_materials_recognized():
    assert extract_attributes_from_text("Pine Raised Bed 4x8")["material"] == "pine"
    assert extract_attributes_from_text("Classic Wood Raised Garden Bed")["material"] == "wood"
