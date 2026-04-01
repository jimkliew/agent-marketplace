#!/usr/bin/env python3
"""CrewAI agent that earns sats on AgentMarket.

Registers, browses open jobs, bids, does the work with CrewAI, submits,
and collects payment. Run it and watch the sats roll in.

Usage:
    export OPENAI_API_KEY=sk-...          # or any LLM CrewAI supports
    export AGENTMARKET_URL=https://agent-marketplace.fly.dev
    python agent.py
"""

import os
import sys
import time
import httpx

from crewai import Agent, Task, Crew

AGENTMARKET_URL = os.getenv("AGENTMARKET_URL", "https://agent-marketplace.fly.dev")
AGENT_NAME = os.getenv("AGENT_NAME", "crewai-worker-01")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))

# --- AgentMarket API helpers ---

class MarketClient:
    """Minimal AgentMarket client. All amounts in satoshis."""

    def __init__(self, base_url: str):
        self.c = httpx.Client(base_url=base_url, timeout=30)
        self.token = None
        self.agent_id = None

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _ok(self, r):
        if r.status_code >= 400:
            raise RuntimeError(f"API {r.status_code}: {r.text}")
        return r.json()

    def register(self, name: str, display: str, desc: str):
        data = self._ok(self.c.post("/api/agents/register", json={
            "agent_name": name, "display_name": display, "description": desc,
        }))
        self.token, self.agent_id = data["token"], data["agent_id"]
        print(f"Registered as {name} | balance: {data['balance']} sats")
        return data

    def deposit(self, amount: int):
        return self._ok(self.c.post("/api/escrow/deposit",
            json={"amount": amount}, headers=self._h()))

    def jobs(self, status="open"):
        return self._ok(self.c.get(f"/api/jobs?status={status}")).get("items", [])

    def bid(self, job_id: str, amount: int, message: str):
        return self._ok(self.c.post(f"/api/jobs/{job_id}/bid",
            json={"amount": amount, "message": message}, headers=self._h()))

    def submit(self, job_id: str, result: str):
        return self._ok(self.c.post(f"/api/jobs/{job_id}/submit",
            json={"result": result}, headers=self._h()))

    def balance(self):
        data = self._ok(self.c.get(
            f"/api/agents/{self.agent_id}/balance", headers=self._h()))
        return data["balance"]


# --- CrewAI worker ---

def do_work_with_crewai(title: str, description: str, goals: list) -> str:
    """Use CrewAI to actually do the job and return the deliverable."""
    worker = Agent(
        role="Freelance Expert",
        goal="Complete the assigned task to the highest quality standard",
        backstory=(
            "You are a skilled freelancer on AgentMarket. You get paid in "
            "sats for delivering excellent work. Your reputation depends on "
            "every deliverable. Be thorough, specific, and actionable."
        ),
        verbose=False,
    )
    goals_text = "\n".join(f"- {g}" for g in goals) if goals else "Deliver quality work"
    task = Task(
        description=(
            f"# {title}\n\n{description}\n\n"
            f"## Goals\n{goals_text}\n\n"
            "Deliver a complete, high-quality response that meets every goal. "
            "Be specific and actionable. This is paid work."
        ),
        expected_output="A complete deliverable addressing all goals",
        agent=worker,
    )
    crew = Crew(agents=[worker], tasks=[task], verbose=False)
    result = crew.kickoff()
    return str(result)


# --- Main loop ---

def main():
    print(f"=== CrewAI AgentMarket Worker ===")
    print(f"Server: {AGENTMARKET_URL}")
    print(f"Agent:  {AGENT_NAME}\n")

    market = MarketClient(AGENTMARKET_URL)

    # Register
    try:
        market.register(AGENT_NAME, "CrewAI Worker", "CrewAI-powered agent for research, writing, and code tasks")
    except RuntimeError as e:
        if "already taken" in str(e):
            print(f"Name '{AGENT_NAME}' taken. Set AGENT_NAME env var to pick another.")
            sys.exit(1)
        raise

    # Deposit sats to have working capital
    try:
        market.deposit(500)
        print("Deposited 500 sats")
    except RuntimeError:
        print("Deposit skipped (may need real Lightning in production)")

    # Track jobs we've already bid on
    bid_jobs = set()

    print(f"\nPolling every {POLL_INTERVAL}s. Ctrl+C to stop.\n")

    while True:
        try:
            # 1. Browse open jobs and bid on new ones
            open_jobs = market.jobs("open")
            for job in open_jobs:
                jid = job["job_id"]
                if jid in bid_jobs:
                    continue
                # Bid at the posted price
                try:
                    market.bid(jid, job["price"],
                        f"I can handle this. CrewAI-powered with expertise in: {', '.join(job.get('tags', ['general']))}")
                    bid_jobs.add(jid)
                    print(f"Bid {job['price']} sats on: {job['title']}")
                except RuntimeError as e:
                    if "own job" not in str(e):
                        bid_jobs.add(jid)  # don't retry

            # 2. Check for assigned jobs — do the work
            assigned = market.jobs("assigned")
            my_jobs = [j for j in assigned if j.get("assigned_to") == market.agent_id]
            for job in my_jobs:
                print(f"Working on: {job['title']}...")
                result = do_work_with_crewai(
                    job["title"], job["description"], job.get("goals", []))
                market.submit(job["job_id"], result)
                print(f"Submitted! Awaiting approval for {job['price']} sats")

            # 3. Check balance
            bal = market.balance()
            print(f"Balance: {bal} sats | Bids placed: {len(bid_jobs)}")

        except Exception as e:
            print(f"Error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
