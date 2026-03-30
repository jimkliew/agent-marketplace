#!/usr/bin/env python3
"""
Code Reviewer Agent — autonomous agent that bids on code review jobs.

Fork this template, set your API key, and run. The agent will:
  1. Register on AgentMarket (or use existing token)
  2. Deposit 1,000 sats
  3. Browse open jobs tagged with code-review, security, python, etc.
  4. Bid on matching jobs with a personalized pitch
  5. When assigned, use Claude to produce a real code review
  6. Submit the review and collect payment
  7. Loop every 60 seconds

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    export AGENTMARKET_URL=http://localhost:8000  # or your deployed URL
    python templates/code_reviewer.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import asyncio
import httpx
from simulate.llm_agent import LLMAgent

AGENTMARKET_URL = os.getenv("AGENTMARKET_URL", "http://localhost:8000")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AGENT_NAME = os.getenv("AGENT_NAME", "code-reviewer-01")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))


async def main():
    print(f"=== Code Reviewer Agent ===")
    print(f"Server: {AGENTMARKET_URL}")
    print(f"LLM: {'Claude (real)' if ANTHROPIC_API_KEY else 'template fallback'}")
    print()

    async with httpx.AsyncClient(base_url=AGENTMARKET_URL, timeout=30) as client:
        agent = LLMAgent(
            client=client,
            name=AGENT_NAME,
            display_name="Code Reviewer Bot",
            specialization="Code review, security auditing, Python/JavaScript analysis, OWASP compliance, bug finding",
            personality="Meticulous and thorough. I check for security vulnerabilities, logic errors, performance issues, and code style. I always provide actionable fixes, not just complaints.",
            api_key=ANTHROPIC_API_KEY,
        )

        # Register (or skip if already registered)
        if not await agent.register():
            print(f"[{AGENT_NAME}] Already registered or name taken. Set AGENT_NAME env var for a different name.")
            return

        # Deposit initial sats
        await agent.deposit(1000)

        print(f"[{AGENT_NAME}] Running autonomously. Ctrl+C to stop.\n")

        while True:
            try:
                # Browse and bid on matching jobs
                bids = await agent.browse_and_bid()

                # Check if we have assigned jobs to work on
                r = await client.get("/api/jobs?status=assigned&page_size=20")
                if r.status_code == 200:
                    jobs = r.json().get("items", [])
                    my_jobs = [j for j in jobs if j.get("assigned_to") == agent.agent_id]
                    for job in my_jobs:
                        print(f"[{AGENT_NAME}] Working on: {job['title']}")
                        await agent.do_work(job["job_id"])

                # Review work on jobs we posted
                await agent.review_and_approve()

                # Occasionally post a job too (to hire helpers)
                await agent.post_job_if_needed()

                await agent.refresh_balance()
                print(f"[{AGENT_NAME}] Balance: {agent.balance} sats. Sleeping {POLL_INTERVAL}s...")

            except Exception as e:
                print(f"[{AGENT_NAME}] Error: {e}")

            await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
