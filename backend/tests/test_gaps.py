"""Unit tests for app/intelligence/gaps.py — pure computation, no DB
fixtures needed.
"""

from app.intelligence.gaps import find_opportunities

SLUGS = ["gardeners-supply", "epic-gardening", "vego-garden"]


def test_finds_a_real_gap_when_competitors_carry_it_and_we_dont():
    cells = [
        ("epic-gardening", "galvanized_steel", "tall", "modular", 3),
        ("vego-garden", "galvanized_steel", "tall", "modular", 2),
    ]
    gaps, strengths = find_opportunities("gardeners-supply", SLUGS, cells, min_count=2)
    assert len(gaps) == 1
    assert gaps[0].material == "galvanized_steel"
    assert gaps[0].own_count == 0
    assert gaps[0].competitor_counts == {"epic-gardening": 3, "vego-garden": 2}
    assert gaps[0].total_competitor_count == 5


def test_single_stray_competitor_sku_is_not_a_gap():
    cells = [("epic-gardening", "aluminum", "shallow", "ground", 1)]
    gaps, _ = find_opportunities("gardeners-supply", SLUGS, cells, min_count=2)
    assert gaps == []


def test_finds_a_real_strength_when_we_have_depth_and_competitors_have_none():
    cells = [("gardeners-supply", "cedar", "shallow", "ground", 5)]
    _, strengths = find_opportunities("gardeners-supply", SLUGS, cells, min_count=2)
    assert len(strengths) == 1
    assert strengths[0].material == "cedar"
    assert strengths[0].own_count == 5
    assert strengths[0].competitor_counts == {}


def test_combo_everyone_has_is_neither_gap_nor_strength():
    cells = [
        ("gardeners-supply", "cedar", "shallow", "ground", 3),
        ("epic-gardening", "cedar", "shallow", "ground", 2),
    ]
    gaps, strengths = find_opportunities("gardeners-supply", SLUGS, cells, min_count=2)
    assert gaps == []
    assert strengths == []


def test_gaps_sorted_by_competitor_total_descending():
    cells = [
        ("epic-gardening", "aluminum", "shallow", "ground", 2),
        ("epic-gardening", "steel", "tall", "modular", 5),
        ("vego-garden", "steel", "tall", "modular", 4),
    ]
    gaps, _ = find_opportunities("gardeners-supply", SLUGS, cells, min_count=2)
    assert [g.material for g in gaps] == ["steel", "aluminum"]


def test_respects_limit():
    cells = [
        (slug, f"material-{i}", "shallow", "ground", 3)
        for i, slug in enumerate(["epic-gardening"] * 20)
    ]
    gaps, _ = find_opportunities("gardeners-supply", SLUGS, cells, min_count=2, limit=5)
    assert len(gaps) == 5
