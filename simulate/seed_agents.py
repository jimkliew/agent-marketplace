#!/usr/bin/env python3
"""
Seed Agents — run 10 diverse agents 24/7 to create marketplace liquidity.

This is the lifeblood of the marketplace. Without activity, no one joins.
These agents create a constant flow of jobs, bids, and completions.

Run alongside the server:
    AGENTMARKET_URL=https://your-instance.fly.dev python -m simulate.seed_agents

Or with real Claude reasoning:
    ANTHROPIC_API_KEY=sk-ant-... python -m simulate.seed_agents
"""

import os
import sys
import asyncio
import random
import time
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from simulate.llm_agent import LLMAgent

AGENTMARKET_URL = os.getenv("AGENTMARKET_URL", "http://localhost:8000")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CYCLE_INTERVAL = int(os.getenv("CYCLE_INTERVAL", "30"))  # seconds between cycles

# 10 diverse seed agents
SEEDS = [
    ("seed-coder", "Coder One", "Python, JavaScript, API development, debugging, testing",
     "Fast coder. Ships clean, tested code. Competitive bidder."),
    ("seed-reviewer", "Code Reviewer", "Security audits, code review, OWASP, bug finding",
     "Thorough reviewer. Finds bugs others miss. Charges fair prices."),
    ("seed-writer", "Tech Writer", "Documentation, guides, tutorials, API docs, copywriting",
     "Clear, concise writer. Makes complex topics accessible."),
    ("seed-analyst", "Data Analyst", "Data analysis, statistics, trend detection, reports",
     "Methodical. Shows work with tables and numbers. Data-driven."),
    ("seed-designer", "UI Designer", "Frontend design, CSS, responsive layouts, UX",
     "Creative and opinionated. Delivers polished, modern designs."),
    ("seed-researcher", "Researcher", "Market research, competitive analysis, literature review",
     "Deep thinker. Comprehensive reports with citations."),
    ("seed-devops", "DevOps Engineer", "Docker, CI/CD, cloud deployment, monitoring, automation",
     "Pragmatic builder. Automates everything. Infrastructure that works."),
    ("seed-qa", "QA Engineer", "Testing, test automation, regression testing, bug reporting",
     "Detail-oriented. Writes tests before fixes. High standards."),
    ("seed-pm", "Project Manager", "Task decomposition, requirements, coordination, planning",
     "Breaks big problems into small tasks. Hires specialists. Reviews carefully."),
    ("seed-security", "Security Specialist", "Penetration testing, vulnerability assessment, compliance",
     "Skeptical and meticulous. Never cuts corners on security."),
]

# Job templates that seed agents will post
JOB_POOL = [
    ("Review authentication module", "Audit the auth system for security vulnerabilities. Check token handling, session management, and access controls.", ["security", "code-review"], 300),
    ("Write API integration guide", "Create a developer guide for integrating with our REST API. Include auth, endpoints, error handling, and code examples.", ["writing", "documentation"], 250),
    ("Analyze user behavior data", "Process user engagement metrics from the past month. Identify trends, drop-off points, and growth opportunities.", ["analysis", "data"], 350),
    ("Build notification system", "Implement a webhook-based notification system. Handle retries, signature verification, and failure tracking.", ["backend", "api"], 400),
    ("Design dashboard mockup", "Create a clean, modern admin dashboard layout. Focus on data visualization and key metrics display.", ["design", "frontend"], 300),
    ("Write test suite for payments", "Create comprehensive tests for the payment/escrow module. Cover happy paths, edge cases, and error scenarios.", ["testing", "qa"], 350),
    ("Research competitor platforms", "Analyze 5 competing agent marketplace platforms. Compare features, pricing, and market positioning.", ["research", "analysis"], 250),
    ("Set up monitoring and alerts", "Configure application monitoring with health checks, error rate tracking, and alert thresholds.", ["devops", "monitoring"], 300),
    ("Optimize database queries", "Review and optimize slow SQL queries. Add missing indexes and improve query patterns.", ["backend", "performance"], 350),
    ("Create onboarding email flow", "Design a 3-email welcome sequence for new agents. Cover registration, first job, and earning tips.", ["writing", "marketing"], 200),
]


async def run_seed_agents():
    print(f"{'='*60}")
    print(f"SEED AGENTS: 10 agents creating marketplace liquidity")
    print(f"Server: {AGENTMARKET_URL}")
    print(f"LLM: {'Claude' if ANTHROPIC_API_KEY else 'template fallback'}")
    print(f"Cycle: every {CYCLE_INTERVAL}s")
    print(f"{'='*60}\n")

    async with httpx.AsyncClient(base_url=AGENTMARKET_URL, timeout=30) as client:
        # Create all agents
        agents = []
        for name, display, spec, personality in SEEDS:
            agent = LLMAgent(client, name, display, spec, personality, ANTHROPIC_API_KEY)
            if await agent.register():
                await agent.deposit(1000)
                agents.append(agent)
            else:
                # Already registered — try to continue (would need token persistence for real use)
                print(f"[{name}] Skipped (already registered or error)")

        if not agents:
            print("No agents registered. Platform may already have seed agents.")
            return

        print(f"\n{len(agents)} seed agents active. Starting marketplace activity...\n")
        cycle = 0

        while True:
            cycle += 1
            t0 = time.time()
            print(f"--- Cycle {cycle} ---")

            # 1. Random agents post jobs (2-3 per cycle)
            posters = random.sample(agents, min(3, len(agents)))
            for poster in posters:
                if poster.balance >= 200:
                    job = random.choice(JOB_POOL)
                    price = min(job[3], poster.balance)
                    try:
                        r = await client.post("/api/jobs", json={
                            "title": job[0], "description": job[1],
                            "goals": ["Complete the task", "Deliver quality results"],
                            "tags": job[2], "price": price,
                        }, headers=poster._auth())
                        if r.status_code == 200:
                            poster.balance -= price
                            print(f"  [Post] {poster.name}: \"{job[0][:35]}\" for {price} sats")
                    except Exception:
                        pass

            # 2. All agents browse and bid
            for agent in agents:
                try:
                    await agent.browse_and_bid()
                except Exception:
                    pass

            # 3. Accept bids on open jobs
            try:
                r = await client.get("/api/jobs?status=open&page_size=20")
                if r.status_code == 200:
                    for job in r.json().get("items", []):
                        poster = next((a for a in agents if a.agent_id == job["poster_id"]), None)
                        if not poster:
                            continue
                        detail = await client.get(f"/api/jobs/{job['job_id']}")
                        if detail.status_code != 200:
                            continue
                        bids = [b for b in detail.json().get("bids", []) if b["status"] == "pending"]
                        if bids:
                            bid = random.choice(bids)
                            await client.post(f"/api/jobs/{job['job_id']}/accept-bid/{bid['bid_id']}", headers=poster._auth())
                            print(f"  [Accept] {poster.name} accepted bid on \"{job['title'][:35]}\"")
            except Exception:
                pass

            # 4. Workers submit on assigned jobs
            try:
                r = await client.get("/api/jobs?status=assigned&page_size=20")
                if r.status_code == 200:
                    for job in r.json().get("items", []):
                        worker = next((a for a in agents if a.agent_id == job.get("assigned_to")), None)
                        if worker:
                            await worker.do_work(job["job_id"])
            except Exception:
                pass

            # 5. Approve completed work
            try:
                r = await client.get("/api/jobs?status=review&page_size=20")
                if r.status_code == 200:
                    for job in r.json().get("items", []):
                        poster = next((a for a in agents if a.agent_id == job["poster_id"]), None)
                        if poster:
                            await client.post(f"/api/jobs/{job['job_id']}/approve", headers=poster._auth())
                            print(f"  [Approve] {poster.name} approved \"{job['title'][:35]}\"")
            except Exception:
                pass

            # 6. Refresh balances
            for agent in agents:
                await agent.refresh_balance()

            elapsed = time.time() - t0
            total_bal = sum(a.balance for a in agents)
            print(f"  [{elapsed:.1f}s] Total balance: {total_bal:,} sats across {len(agents)} agents")

            await asyncio.sleep(CYCLE_INTERVAL)


if __name__ == "__main__":
    asyncio.run(run_seed_agents())
