"""Deterministic assortment gap/opportunity detection — surfaces where the
own brand lacks a material/height/form combination that competitors carry
in real depth, and the reverse (where we have depth they lack entirely).

Pure computation over the same (competitor_slug, material, height_band,
form, count) cells the assortment matrix already serves (see
app/api/intelligence.py's get_matrix) — no judgment calls beyond a simple
count threshold, so every finding traces directly to recorded, classified
SKUs. This is exactly the project's "explain deterministic analysis, don't
invent it" rule applied to opportunity-finding: a gap is a fact about what's
missing, not an AI guess about what might sell.
"""

from dataclasses import dataclass, field


@dataclass
class Opportunity:
    material: str
    height_band: str
    form: str
    kind: str  # "gap" (own brand lacks it, competitors carry it) | "strength" (reverse)
    own_count: int
    competitor_counts: dict[str, int] = field(default_factory=dict)  # slug -> count, nonzero only

    @property
    def total_competitor_count(self) -> int:
        return sum(self.competitor_counts.values())


def find_opportunities(
    own_brand_slug: str,
    all_slugs: list[str],
    cells: list[tuple[str, str, str, str, int]],
    *,
    min_count: int = 2,
    limit: int = 10,
) -> tuple[list[Opportunity], list[Opportunity]]:
    """cells is (competitor_slug, material, height_band, form, count) — the
    same rows the assortment matrix endpoint returns (only combos that
    actually occur, always count >= 1). all_slugs is every brand this
    workbench tracks, own brand included — passed explicitly rather than
    inferred from `cells` alone, since a brand with zero SKUs in a given
    combo simply has no row for it, and "no competitor carries this" needs
    to be distinguished from "no competitor data exists at all."

    Returns (gaps, strengths), each sorted by how many SKUs are on the
    other side of the finding (biggest signal first), capped to `limit`.
    min_count gates out noise from a single stray SKU: a combo only counts
    as a real gap/strength once the side that "has it" carries at least
    this many recorded products, not just one.
    """
    other_slugs = [s for s in all_slugs if s != own_brand_slug]

    by_combo: dict[tuple[str, str, str], dict[str, int]] = {}
    for slug, material, height_band, form, count in cells:
        by_combo.setdefault((material, height_band, form), {})[slug] = count

    gaps: list[Opportunity] = []
    strengths: list[Opportunity] = []
    for (material, height_band, form), counts in by_combo.items():
        own_count = counts.get(own_brand_slug, 0)
        competitor_counts = {slug: counts[slug] for slug in other_slugs if counts.get(slug, 0) > 0}
        competitor_total = sum(competitor_counts.values())

        if own_count == 0 and competitor_total >= min_count:
            gaps.append(
                Opportunity(
                    material=material,
                    height_band=height_band,
                    form=form,
                    kind="gap",
                    own_count=0,
                    competitor_counts=competitor_counts,
                )
            )
        elif own_count >= min_count and competitor_total == 0 and other_slugs:
            strengths.append(
                Opportunity(
                    material=material,
                    height_band=height_band,
                    form=form,
                    kind="strength",
                    own_count=own_count,
                    competitor_counts={},
                )
            )

    gaps.sort(key=lambda o: o.total_competitor_count, reverse=True)
    strengths.sort(key=lambda o: o.own_count, reverse=True)
    return gaps[:limit], strengths[:limit]
