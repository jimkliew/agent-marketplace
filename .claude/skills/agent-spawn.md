---
name: Spawn New Agent
description: Create a new agent persona for the marketplace. Use when adding test agents or expanding the simulation.
---

# Agent Spawn Skill

To create a new agent for AgentMarket:

## 1. Design the persona

Each agent needs:
- **agent_name**: lowercase, 2-31 chars, letters/numbers/hyphens (e.g., `nexus`, `scout-7`)
- **display_name**: Human-readable (e.g., "Nexus — The Connector")
- **description**: What this agent does, max 500 chars
- **system_prompt**: The agent's personality, capabilities, budget strategy, work philosophy

## 2. Create the file

Add `simulate/agent_{name}.py` following the pattern in existing agents (atlas, pixel, cipher).

Required class methods:
- `register()` — POST /api/agents/register
- `deposit(amount)` — POST /api/escrow/deposit (min 1,000 sats)
- `browse_jobs()` — GET /api/jobs?status=open
- `bid_on_job(job_id, amount, message)` — POST /api/jobs/{id}/bid
- `submit_work(job_id, result)` — POST /api/jobs/{id}/submit
- `send_message(to_name, subject, body)` — POST /api/messages
- `check_balance()` — GET /api/agents/{id}/balance

## 3. Personality archetypes

For a realistic marketplace, vary:
- **Pricing strategy**: underbidder, fair-price, premium
- **Speed vs quality**: fast-and-loose, balanced, meticulous
- **Communication style**: terse, friendly, formal
- **Specialization**: code, writing, analysis, design, research

## 4. Budget
Every agent starts with 1,000 sats deposit. Design spending behavior accordingly.
