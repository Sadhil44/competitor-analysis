FROM python:3.12-slim

# System deps for Playwright's browser binaries (Chromium) at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml ./
# --group dev pulls in pytest/pytest-asyncio/httpx/ruff too — this image
# also runs the test suite (docker compose exec backend pytest), and
# there's no separate CI/test image at this project's scale.
RUN uv pip install --system --no-cache -e . --group dev
RUN playwright install --with-deps chromium

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
