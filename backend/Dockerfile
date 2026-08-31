FROM python:3.12-slim

# System deps for Playwright's browser binaries (Chromium) at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY backend/pyproject.toml ./
# --group dev pulls in pytest/pytest-asyncio/httpx/ruff too — this image
# also runs the test suite (docker compose exec backend pytest), and
# there's no separate CI/test image at this project's scale.
RUN uv pip install --system --no-cache -e . --group dev
RUN playwright install --with-deps chromium

COPY backend/ .
# config/competitors.yaml and own_brands.yaml live at the repo root, not
# under backend/ — baked in here (at the same /config path
# COMPETITORS_CONFIG_PATH/OWN_BRANDS_CONFIG_PATH already expect) so this
# image is self-contained for a platform deploy (Railway) with no bind
# mount available. Local docker-compose still bind-mounts ./config:/config
# on top of this at runtime, for editing config without a rebuild — see
# docker-compose.yml. Build context is the repo root (not backend/) so
# this COPY can reach it — see docker-compose.yml's build.context and
# Railway's root/build settings.
COPY config/ /config/

EXPOSE 8000

# Shell form (not exec-form CMD) so $PORT actually expands — Railway (and
# most PaaS Docker deploys) inject their own PORT at runtime rather than
# trusting EXPOSE, and don't all agree on 8000; local docker-compose has no
# PORT set, so this falls back to 8000 same as before.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --reload
