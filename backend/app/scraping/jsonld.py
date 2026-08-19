"""Shared JSON-LD parsing helpers. schema.org data in the wild ships as a
single object, a list of objects, or a list/object wrapped in an @graph
node — extractor.py (product data) and discovery.py (page classification)
both need to walk that shape, so it lives here once instead of twice.
"""

import json
from collections.abc import Iterator
from typing import Any

from bs4 import BeautifulSoup


def extract_jsonld_blocks(soup: BeautifulSoup) -> list[Any]:
    """Parse every <script type="application/ld+json"> block on the page.
    A block with malformed JSON is skipped, not raised — real pages
    sometimes ship broken JSON-LD, and one bad block shouldn't lose every
    other signal on the page.
    """
    blocks = []
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string
        if not raw:
            continue
        try:
            blocks.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return blocks


def iter_jsonld_nodes(data: Any) -> Iterator[dict]:
    """Yield every node (dict) in a parsed JSON-LD payload, flattening
    lists and @graph wrappers — the shapes schema.org markup actually
    ships in, per the docstring above.
    """
    if isinstance(data, list):
        for item in data:
            yield from iter_jsonld_nodes(item)
    elif isinstance(data, dict):
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from iter_jsonld_nodes(item)
        else:
            yield data


def node_types(node: dict) -> list[str]:
    raw_type = node.get("@type")
    if isinstance(raw_type, str):
        return [raw_type]
    if isinstance(raw_type, list):
        return [t for t in raw_type if isinstance(t, str)]
    return []
