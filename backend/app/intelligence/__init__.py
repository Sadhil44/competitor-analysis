"""Attribute normalization and cross-competitor comparison logic for
structured product comparison (e.g. the raised-bed workbench) — deliberately
separate from app/api and app/scraping: this package owns "what does this
product mean" (normalized material/height/form/etc. and how two products
score as comparable), not fetching or serving.
"""

# The three competitors the raised-bed workbench compares — see
# config/competitors.yaml for their crawl targets. Shared between
# app/api/intelligence.py and app/agent/tools/__init__.py so the API and the
# agent's compare_assortment tool can never silently drift out of scope sync.
WORKBENCH_SLUGS = ["gardeners-supply", "epic-gardening", "vego-garden"]
RAISED_BED_TYPES = ("raised_bed", "elevated_planter")
