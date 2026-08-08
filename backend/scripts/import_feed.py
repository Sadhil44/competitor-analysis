"""One-off CLI to load the first-party pricing feed CSV.

Run inside the backend container (it needs DATABASE_URL/config exactly like
the app does), with the CSV placed somewhere under backend/ so the existing
`./backend:/app` docker-compose volume mount makes it visible — e.g.
backend/data/products.csv (backend/data/ is gitignored):

    docker compose exec backend python scripts/import_feed.py data/products.csv
"""

import asyncio
import sys
from pathlib import Path

from app.db.session import async_session_factory
from app.scraping.feed_import import import_product_feed, seed_own_brands


async def main(csv_path: Path) -> None:
    async with async_session_factory() as session:
        await seed_own_brands(session)
        await import_product_feed(session, csv_path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"Usage: python {sys.argv[0]} <path-to-feed.csv>")
    path = Path(sys.argv[1])
    if not path.is_file():
        raise SystemExit(f"No such file: {path}")
    asyncio.run(main(path))
