"""
LLM Simulation — autonomous agents that think with Claude.

Each agent uses Claude to:
  - Decide which jobs to bid on
  - Write personalized bid messages
  - Generate real deliverables
  - Post their own jobs when they need help
  - Review and approve/dispute work

Usage:
    # With API key (real Claude reasoning):
    ANTHROPIC_API_KEY=sk-... python -m simulate.llm_sim --agents 5

    # Without API key (graceful fallback with template responses):
    python -m simulate.llm_sim --agents 5
"""

import argparse
import asyncio
import random
import time
import os
import httpx
from simulate.llm_agent import LLMAgent

API_BASE = "http://localhost:8000"

# Diverse agent personas
PERSONAS = [
    ("analyst", "Nova — Data Analyst", "Data analysis, statistics, trend detection, visualization",
     "Methodical and precise. Loves finding patterns in data. Charges fair prices."),
    ("coder", "Spark — Code Developer", "Python, JavaScript, API development, debugging",
     "Fast coder, ships clean code. Slightly underbids to win jobs. Friendly."),
    ("writer", "Echo — Technical Writer", "Documentation, guides, copywriting, editing",
     "Clear, concise writer. Adapts tone to audience. Values quality over speed."),
    ("security", "Shield — Security Auditor", "Security audits, penetration testing, code review, compliance",
     "Skeptical and thorough. Never cuts corners. Charges premium prices."),
    ("designer", "Prism — UI/UX Designer", "Interface design, CSS, user experience, wireframing",
     "Creative and opinionated about design. Delivers polished work."),
    ("researcher", "Sage — Research Agent", "Market research, competitive analysis, literature review",
     "Deep thinker. Asks clarifying questions before starting. Comprehensive reports."),
    ("devops", "Forge — Infrastructure Engineer", "Docker, CI/CD, cloud deployment, monitoring",
     "Pragmatic builder. Automates everything. Ships infrastructure that just works."),
    ("ml-eng", "Tensor — ML Engineer", "Machine learning, model training, data pipelines, evaluation",
     "Obsessed with metrics. Always benchmarks. Loves optimization."),
    ("qa", "Sentinel — QA Engineer", "Testing, test automation, bug hunting, regression testing",
     "Finds bugs others miss. Writes tests before fixes. Extremely detail-oriented."),
    ("pm", "Compass — Project Manager", "Task decomposition, coordination, requirements, planning",
     "Breaks big problems into small tasks. Hires specialists. Reviews carefully."),
]

# Seed jobs that the PM agent will post
SEED_JOBS = [
    {"title": "Analyze our API error rates this week",
     "description": "Pull error logs from the past 7 days, categorize by type, and produce a report with the top 5 issues and recommended fixes.",
     "goals": ["Categorize errors by type", "Identify top 5 issues", "Recommend fixes for each"],
     "tags": ["analysis", "api", "monitoring"], "price": 300},
    {"title": "Write a getting-started guide for new developers",
     "description": "Create a clear, beginner-friendly guide covering setup, authentication, and making your first API call.",
     "goals": ["Cover environment setup", "Explain authentication", "Include working code examples", "Keep under 800 words"],
     "tags": ["writing", "documentation"], "price": 250},
    {"title": "Security review of the payment module",
     "description": "Audit the escrow and payment code for vulnerabilities. Check for injection, auth bypass, race conditions, and data leaks.",
     "goals": ["Check for OWASP Top 10", "Review escrow atomicity", "Test for race conditions", "Deliver findings report"],
     "tags": ["security", "code-review", "audit"], "price": 400},
]


async def run_llm_sim(num_agents: int, num_rounds: int):
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    mode = "Claude-powered" if api_key else "template fallback (set ANTHROPIC_API_KEY for real AI)"

    print(f"\n{'='*60}")
    print(f"LLM SIMULATION: {num_agents} agents, {num_rounds} rounds")
    print(f"Mode: {mode}")
    print(f"{'='*60}\n")

    async with httpx.AsyncClient(base_url=API_BASE, timeout=60) as client:
        # Create agents with random personas
        agents = []
        used_personas = []
        for i in range(num_agents):
            p = PERSONAS[i % len(PERSONAS)]
            suffix = f"-{i // len(PERSONAS)}" if i >= len(PERSONAS) else ""
            name = f"{p[0]}{suffix}-{i:03d}"
            agents.append(LLMAgent(
                client, name, p[1], p[2], p[3], api_key,
            ))

        # Phase 1: Register & deposit
        t0 = time.time()
        results = await asyncio.gather(*[a.register() for a in agents])
        registered = [a for a, ok in zip(agents, results) if ok]
        print(f"[Register] {len(registered)}/{num_agents} in {time.time()-t0:.2f}s")

        t0 = time.time()
        await asyncio.gather(*[a.deposit(1000) for a in registered])
        print(f"[Deposit]  {len(registered)} x 1,000 sats in {time.time()-t0:.2f}s")

        # Phase 2: PM agent posts seed jobs
        pm = registered[0] if registered else None
        if pm:
            print(f"\n[Seed] {pm.name} posts initial jobs...")
            for job in SEED_JOBS[:min(3, len(SEED_JOBS))]:
                if pm.balance >= job["price"]:
                    r = await client.post("/api/jobs", json=job, headers=pm._auth())
                    if r.status_code == 200:
                        pm.balance -= job["price"]
                        print(f"  Posted: \"{job['title']}\" for {job['price']} sats")

        # Phase 3: Autonomous rounds
        for round_num in range(1, num_rounds + 1):
            print(f"\n--- Round {round_num}/{num_rounds} ---")

            # Each agent browses and bids
            t0 = time.time()
            random.shuffle(registered)
            for agent in registered:
                await agent.autonomous_cycle()
            print(f"  [Cycle] {len(registered)} agents acted in {time.time()-t0:.2f}s")

            # Accept bids on open jobs (poster picks first bid for simplicity)
            jobs_r = await client.get("/api/jobs?status=open&page_size=50")
            if jobs_r.status_code == 200:
                open_jobs = jobs_r.json().get("items", [])
                for job in open_jobs:
                    poster = next((a for a in registered if a.agent_id == job["poster_id"]), None)
                    if not poster:
                        continue
                    detail_r = await client.get(f"/api/jobs/{job['job_id']}")
                    if detail_r.status_code != 200:
                        continue
                    bids = detail_r.json().get("bids", [])
                    pending = [b for b in bids if b["status"] == "pending"]
                    if pending:
                        bid = pending[0]
                        r = await client.post(
                            f"/api/jobs/{job['job_id']}/accept-bid/{bid['bid_id']}",
                            headers=poster._auth())
                        if r.status_code == 200:
                            print(f"  [Accept] {poster.name} accepted bid on \"{job['title'][:35]}\"")

            # Workers do work on assigned jobs
            assigned_r = await client.get("/api/jobs?status=assigned&page_size=50")
            if assigned_r.status_code == 200:
                assigned_jobs = assigned_r.json().get("items", [])
                for job in assigned_jobs:
                    worker = next((a for a in registered if a.agent_id == job.get("assigned_to")), None)
                    if worker:
                        await worker.do_work(job["job_id"])

            # Posters review and approve
            for agent in registered:
                await agent.review_and_approve()

        # Final stats
        print(f"\n{'='*60}")
        print("LLM SIMULATION COMPLETE")
        print(f"{'='*60}")

        for a in registered:
            await a.refresh_balance()

        total_deposited = len(registered) * 1000
        total_balances = sum(a.balance for a in registered)
        total_fees = total_deposited - total_balances

        stats = (await client.get("/api/public/stats")).json()

        print(f"  Agents:        {len(registered)}")
        print(f"  Total deposit: {total_deposited:,} sats")
        print(f"  In balances:   {total_balances:,} sats")
        print(f"  Platform fees: {total_fees:,} sats (6%)")
        print(f"  In escrow:     {stats['escrow_held']:,} sats")
        print(f"  Jobs:          {stats['total_jobs']} ({stats['completed_jobs']} completed)")
        print(f"  Events:        {stats['total_events']}")
        print(f"  Integrity:     {'PASS' if total_balances + stats['escrow_held'] + total_fees == total_deposited else 'FAIL'}")

        # Top earners
        leaders = (await client.get("/api/public/leaderboard")).json()
        if leaders:
            print(f"\n  Top earners:")
            for i, l in enumerate(leaders[:5]):
                a = next((ag for ag in registered if ag.agent_id == l["agent_id"]), None)
                print(f"    {i+1}. {l['agent_name']:25s} rep={l['reputation']:.1f}  bal={a.balance if a else '?'} sats")


def main():
    parser = argparse.ArgumentParser(description="AgentMarket LLM Simulation")
    parser.add_argument("--agents", type=int, default=5, help="Number of agents (default: 5)")
    parser.add_argument("--rounds", type=int, default=2, help="Number of rounds (default: 2)")
    args = parser.parse_args()
    asyncio.run(run_llm_sim(args.agents, args.rounds))


if __name__ == "__main__":
    main()
