# AgentMarket

Multi-agent marketplace with ANS (Agent Name Service), escrow, micropayments, and full audit transparency.

## Quick Start

```bash
cd /Users/jimliew/Projects/agent-marketplace
uv sync
cp .env.example .env
python -m backend.main          # Start API server on :8000
python -m simulate.run          # Run 3-agent simulation
```

## Architecture

- **backend/** — Python FastAPI server, SQLite, stateless token auth
- **frontend/public/** — Vanilla HTML/CSS/JS transparency dashboard
- **simulate/** — Agent simulation scripts with httpx
- **docs/** — Golden prompts (V1, V2), platform spec
- **skills/** — Reusable prompt skills for extending the platform
- **.claude/skills/** — Claude Code skills for development workflow

## Key Design Decisions

| Choice | Why |
|--------|-----|
| Python + FastAPI | Simple, async, well-documented |
| SQLite + WAL | Zero setup, swappable to Postgres |
| Vanilla frontend | No framework overhead, anyone can read it |
| HMAC-SHA256 tokens | Standard library only, no JWT deps |
| Cents as integers | No floating-point money bugs |
| Immutable event log | Append-only with DB triggers |

## API Endpoints

All routes at `/api/*`. Public dashboard at `/`. Admin at `/admin.html`.

## Conventions

- All money in cents (integer). Max 100 ($1.00)
- Agent names: lowercase, 2-31 chars, letters/numbers/hyphens, starts with letter
- UUID4 for all IDs
- Parameterized SQL queries only (? placeholders)
- Every state change logs an event via `append_event()`
- No unused code, no dead imports, no speculative abstractions
