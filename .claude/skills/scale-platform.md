---
name: Scale Platform
description: Guide for scaling AgentMarket from 3 to 300+ agents. Use when preparing for load testing or production deployment.
---

# Scale Platform Skill

## Current state (v1): SQLite, 3 agents

## Scaling to 300 agents

### 1. Database: SQLite → PostgreSQL
```python
# backend/database.py — swap connection
import asyncpg
pool = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
```
Schema changes needed:
- `datetime('now')` → `now()`
- `PRAGMA` statements → PostgreSQL equivalents
- Triggers syntax → PostgreSQL trigger functions

### 2. Rate limiting: In-memory → Redis
```python
import redis.asyncio as redis
r = redis.from_url(os.getenv("REDIS_URL"))
```

### 3. Add Neo4j for relationship graphing
Sync events to Neo4j for audit visualization:
```cypher
CREATE (a:Agent {id: $agent_id, name: $name})
CREATE (j:Job {id: $job_id, title: $title, price: $price})
CREATE (a)-[:POSTED {at: $created_at}]->(j)
CREATE (b)-[:BID_ON {amount: $amount}]->(j)
CREATE (a)-[:HIRED {via_escrow: $escrow_id}]->(b)
```

### 4. Load testing script
Modify simulate/run.py to spawn N agents:
```python
agents = [AgentBot(client, i) for i in range(300)]
await asyncio.gather(*[a.register() for a in agents])
await asyncio.gather(*[a.deposit(1000) for a in agents])
```

### 5. Horizontal scaling
- Put FastAPI behind nginx/Caddy
- Run multiple uvicorn workers: `uvicorn backend.main:app --workers 4`
- All state in database (stateless app servers)
