# competitor-analysis

An AI agent system for horticultural-industry competitor research: product/SKU-level
pricing tracking over time, SWOT analysis generation per competitor, and tracking
"developments" (news, launches, promotions, PR) — combining a scheduled scraping
pipeline with an on-demand, tool-using AI agent.

## Architecture

```
Next.js Dashboard (TS)  →  FastAPI Backend (Python)  →  Postgres + pgvector
                                    │
                        ┌───────────┴───────────┐
                        │                       │
              Agent Orchestrator         Scraping Pipeline
              (Claude Agent SDK)         (APScheduler cron)
              ├─ swot_agent (subagent)   Playwright fetch →
              ├─ developments_agent      LLM structured extraction
              │  (subagent)              (Pydantic schemas) →
              └─ tools: query_price_     writes Product /
                 history, search_        PriceObservation rows
                 developments (RAG),
                 search_web, fetch_page
```

`config/competitors.yaml` is the single source of truth for which competitors are
tracked and where to crawl for each — the system is generic/config-driven, not
hardcoded to specific companies.

## Stack

- **Backend**: Python, FastAPI, SQLAlchemy (async) + Alembic, Postgres + pgvector,
  Playwright, Claude Agent SDK, Voyage AI embeddings, APScheduler.
- **Frontend**: Next.js 16 (App Router), React 19, TypeScript, Tailwind, Recharts.
- **Dev environment**: Docker Compose.

## Local development

1. Copy `.env.example` to `.env` and fill in `ANTHROPIC_API_KEY` / `VOYAGE_API_KEY`
   (required from Phase 3 onward; not needed to boot the stack itself).
2. `docker compose up`
   - Postgres (with pgvector) on `localhost:5432`
   - Backend API on `http://localhost:8000` (health check: `GET /health`)
   - Frontend dashboard on `http://localhost:3000`

## Project layout

```
config/competitors.yaml   # competitor + crawl-target config (source of truth)
backend/app/
  api/                     # FastAPI routers
  models/                  # SQLAlchemy models
  schemas/                 # Pydantic schemas
  db/                       # session + Alembic migrations
  scraping/                 # Playwright fetchers + LLM structured extraction
  scheduler/                 # APScheduler jobs
  agent/                      # orchestrator, subagents, tools
  core/                        # settings + competitors.yaml loader
frontend/app/                  # Next.js App Router pages
```

## Build status

Being built in phases — see the phase plan for current status:
0. Scaffolding & config ← current
1. Data model + single-competitor scraping
2. Pricing storage + trend API
3. Agent + SWOT/developments generation
4. Dashboard
5. Scheduling/automation
6. Observability & polish
