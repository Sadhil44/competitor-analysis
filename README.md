# competitor-analysis

An AI agent system for horticultural-industry competitor research: product/SKU-level
pricing tracking over time, SWOT analysis generation per competitor, and tracking
"developments" (news, launches, promotions, PR) and promotional campaigns — combining
an automated scraping pipeline with an on-demand, tool-using AI agent.

## Architecture

```
Next.js Dashboard (TS)  →  FastAPI Backend (Python)  →  Postgres + pgvector
                                    │
                  ┌─────────────────┼─────────────────┐
                  │                 │                 │
         Agent Orchestrator   Scraping Pipeline   Scheduler
         (LangGraph)          Playwright fetch →  (APScheduler cron,
         ├─ general Q&A       LLM structured       one job per active
         ├─ swot_agent        extraction →         competitor, driven
         ├─ developments_     Product /             by config/
         │  agent             PriceObservation      competitors.yaml)
         └─ tools: price      rows, plus a bulk
            history, RAG      first-party pricing
            search, live      feed import for
            web search        our own brands
```

A `classify` node routes each question to the right subagent; each subagent only has
the tools it's allowed to call, enforced by the graph itself rather than by prompt
instruction alone. `config/competitors.yaml` is the single source of truth for which
competitors are tracked, where to crawl each one, and on what cadence — the system is
generic/config-driven, not hardcoded to specific companies.

## Stack

- **Backend**: Python, FastAPI, SQLAlchemy (async) + Alembic, Postgres + pgvector,
  Playwright, LangGraph + LangChain tools (Claude models), Voyage AI embeddings,
  APScheduler.
- **Frontend**: Next.js 16 (App Router), React 19, TypeScript, Tailwind, Recharts.
- **Dev environment**: Docker Compose.

## Local development

1. Copy `.env.example` to `.env` and fill in `ANTHROPIC_API_KEY` / `VOYAGE_API_KEY`.
2. `docker compose up`
   - Postgres (with pgvector) on `localhost:5432`
   - Backend API on `http://localhost:8000` (health check: `GET /health`)
   - Frontend dashboard on `http://localhost:3000`

Each active competitor in `config/competitors.yaml` gets its own recurring crawl job
on startup, on that entry's `crawl.cadence_cron` schedule. `GET /scheduler/jobs` lists
what's registered and when it next runs; `POST /scheduler/crawl/{slug}` kicks one off
immediately instead of waiting for its cron time.

## Deployment

Frontend on Vercel, backend + Postgres on Railway:

- **Postgres**: deploy the `pgvector/pgvector:pg17` image as a Railway service (not
  Railway's default Postgres template, which doesn't include the pgvector extension)
  with a persistent volume at `/var/lib/postgresql/data`.
- **Backend**: deploy `backend/Dockerfile` with the build context set to the repo
  root (it needs `config/*.yaml`, which live outside `backend/`). Set `DATABASE_URL`
  to the Postgres service, `ANTHROPIC_API_KEY`/`VOYAGE_API_KEY`, and `FRONTEND_ORIGINS`
  to the deployed Vercel URL. The scheduler starts automatically with the app —
  no separate worker service needed at this scale.
- **Frontend**: deploy `frontend/` on Vercel. Set `INTERNAL_API_URL` and
  `NEXT_PUBLIC_API_URL` to the deployed backend's public URL.

## Project layout

```
config/competitors.yaml   # competitor + crawl-target + cadence config (source of truth)
config/own_brands.yaml    # own-brand identity mapping for the first-party pricing feed
backend/app/
  api/                     # FastAPI routers
  models/                  # SQLAlchemy models
  schemas/                 # Pydantic schemas
  db/                       # session + Alembic migrations
  scraping/                 # Playwright fetchers, discovery, LLM structured extraction
  intelligence/               # cross-competitor matching, price-move detection, search
  scheduler/                    # APScheduler wiring — one cron job per active competitor
  agent/                          # LangGraph orchestrator, subagents, tools
  core/                            # settings + competitors.yaml/own_brands.yaml loaders
frontend/app/                      # Next.js App Router pages
frontend/components/                # shared UI (chat, charts, markdown rendering)
```
