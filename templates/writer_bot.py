#!/usr/bin/env python3
"""
Writer Bot Agent — autonomous agent that bids on writing and documentation jobs.

Specializes in: technical writing, documentation, guides, copywriting, editing.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    export AGENTMARKET_URL=http://localhost:8000
    python templates/writer_bot.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import asyncio
import httpx
from simulate.llm_agent import LLMAgent

AGENTMARKET_URL = os.getenv("AGENTMARKET_URL", "http://localhost:8000")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AGENT_NAME = os.getenv("AGENT_NAME", "writer-bot-01")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))


async def main():
    print(f"=== Writer Bot Agent ===")
    print(f"Server: {AGENTMARKET_URL}")
    print(f"LLM: {'Claude (real)' if ANTHROPIC_API_KEY else 'template fallback'}")
    print()

    async with httpx.AsyncClient(base_url=AGENTMARKET_URL, timeout=30) as client:
        agent = LLMAgent(
            client=client,
            name=AGENT_NAME,
            display_name="Writer Bot",
            specialization="Technical writing, documentation, API guides, onboarding content, copywriting, editing, blog posts",
            personality="Clear, concise, and engaging. I adapt my tone to the audience — technical for developers, friendly for end users. I always structure content with headers, bullet points, and examples. Quality over speed.",
            api_key=ANTHROPIC_API_KEY,
        )

        if not await agent.register():
            print(f"[{AGENT_NAME}] Already registered or name taken.")
            return

        await agent.deposit(1000)
        print(f"[{AGENT_NAME}] Running autonomously. Ctrl+C to stop.\n")

        while True:
            try:
                await agent.browse_and_bid()

                r = await client.get("/api/jobs?status=assigned&page_size=20")
                if r.status_code == 200:
                    for job in r.json().get("items", []):
                        if job.get("assigned_to") == agent.agent_id:
                            print(f"[{AGENT_NAME}] Writing: {job['title']}")
                            await agent.do_work(job["job_id"])

                await agent.review_and_approve()
                await agent.post_job_if_needed()
                await agent.refresh_balance()
                print(f"[{AGENT_NAME}] Balance: {agent.balance} sats. Sleeping {POLL_INTERVAL}s...")
            except Exception as e:
                print(f"[{AGENT_NAME}] Error: {e}")

            await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
