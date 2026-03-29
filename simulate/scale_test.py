"""
Scalable simulation — run N agents with dynamic job posting, bidding, and payments.
Not hardcoded. Agents are generated with random specializations and behaviors.

Usage:
    python -m simulate.scale_test              # default 10 agents
    python -m simulate.scale_test --agents 50
    python -m simulate.scale_test --agents 300 --rounds 5
"""

import argparse
import asyncio
import random
import time
import httpx

API_BASE = "http://localhost:8000"

# Agent persona templates — randomly assigned
SPECIALIZATIONS = [
    ("code-review", "Code Reviewer", ["code-review", "security", "python"]),
    ("data-analyst", "Data Analyst", ["analysis", "data", "statistics"]),
    ("writer", "Content Writer", ["writing", "documentation", "copywriting"]),
    ("designer", "UI Designer", ["design", "frontend", "css"]),
    ("researcher", "Researcher", ["research", "analysis", "report"]),
    ("qa-tester", "QA Tester", ["testing", "qa", "automation"]),
    ("devops-eng", "DevOps Engineer", ["devops", "infrastructure", "docker"]),
    ("ml-engineer", "ML Engineer", ["ml", "ai", "model-training"]),
    ("security-auditor", "Security Auditor", ["security", "audit", "compliance"]),
    ("api-developer", "API Developer", ["api", "backend", "integration"]),
]

JOB_TEMPLATES = [
    ("Review Python module for bugs", "Check this Python module for common bugs, edge cases, and performance issues.", ["code-review", "python"]),
    ("Analyze user engagement data", "Process user engagement metrics and produce a summary report with trends.", ["analysis", "data"]),
    ("Write API documentation", "Create clear, concise API docs covering all endpoints with examples.", ["writing", "documentation"]),
    ("Design landing page mockup", "Create a clean, modern landing page design for an AI product.", ["design", "frontend"]),
    ("Research competitor pricing", "Research and compare pricing models of 5 similar platforms.", ["research", "analysis"]),
    ("Write integration tests", "Write comprehensive integration tests for the payment module.", ["testing", "qa"]),
    ("Set up CI/CD pipeline", "Configure GitHub Actions for automated testing and deployment.", ["devops", "infrastructure"]),
    ("Train classification model", "Fine-tune a text classification model on labeled support tickets.", ["ml", "ai"]),
    ("Audit authentication flow", "Review auth implementation for OWASP Top 10 vulnerabilities.", ["security", "audit"]),
    ("Build webhook integration", "Create a webhook handler for processing payment notifications.", ["api", "backend"]),
]


class DynamicAgent:
    """A dynamically generated agent with random specialization."""

    def __init__(self, client: httpx.AsyncClient, index: int):
        self.client = client
        self.index = index
        spec = random.choice(SPECIALIZATIONS)
        self.name = f"{spec[0]}-{index:04d}"
        self.display = f"{spec[1]} #{index}"
        self.tags = spec[2]
        self.token = None
        self.agent_id = None
        self.balance = 0
        self.jobs_posted = 0
        self.jobs_completed = 0

    def _auth(self):
        return {"Authorization": f"Bearer {self.token}"}

    async def register(self):
        r = await self.client.post("/api/agents/register", json={
            "agent_name": self.name,
            "display_name": self.display,
            "description": f"Specializes in {', '.join(self.tags)}",
        })
        if r.status_code != 200:
            return False
        data = r.json()
        self.token = data["token"]
        self.agent_id = data["agent_id"]
        return True

    async def deposit(self, amount=1000):
        r = await self.client.post("/api/escrow/deposit",
            json={"amount": amount}, headers=self._auth())
        if r.status_code == 200:
            self.balance = r.json()["new_balance"]
        return r.status_code == 200

    async def post_job(self):
        if self.balance < 100:
            return None
        template = random.choice(JOB_TEMPLATES)
        price = random.randint(50, min(300, self.balance))
        r = await self.client.post("/api/jobs", json={
            "title": template[0],
            "description": template[1],
            "goals": ["Complete the task", "Deliver quality results"],
            "tags": template[2],
            "price": price,
        }, headers=self._auth())
        if r.status_code == 200:
            self.balance -= price
            self.jobs_posted += 1
            return r.json()["job_id"]
        return None

    async def bid_on_job(self, job_id, price):
        amount = max(1, price - random.randint(0, price // 5))  # bid at or slightly under
        r = await self.client.post(f"/api/jobs/{job_id}/bid", json={
            "amount": amount,
            "message": f"I specialize in {random.choice(self.tags)}. I can deliver quality work.",
        }, headers=self._auth())
        return r.status_code == 200

    async def accept_first_bid(self, job_id):
        r = await self.client.get(f"/api/jobs/{job_id}")
        if r.status_code != 200:
            return False
        bids = r.json().get("bids", [])
        pending = [b for b in bids if b["status"] == "pending"]
        if not pending:
            return False
        bid = random.choice(pending)
        r = await self.client.post(f"/api/jobs/{job_id}/accept-bid/{bid['bid_id']}",
            headers=self._auth())
        return r.status_code == 200

    async def submit_work(self, job_id):
        r = await self.client.post(f"/api/jobs/{job_id}/submit", json={
            "result": f"Completed by {self.name}. Deliverable: analysis report with findings and recommendations. All goals met.",
        }, headers=self._auth())
        return r.status_code == 200

    async def approve_job(self, job_id):
        r = await self.client.post(f"/api/jobs/{job_id}/approve", headers=self._auth())
        if r.status_code == 200:
            self.jobs_completed += 1
        return r.status_code == 200

    async def refresh_balance(self):
        r = await self.client.get(f"/api/agents/{self.agent_id}/balance", headers=self._auth())
        if r.status_code == 200:
            self.balance = r.json()["balance"]


async def run_scale_test(num_agents: int, num_rounds: int):
    print(f"\n{'='*60}")
    print(f"SCALE TEST: {num_agents} agents, {num_rounds} rounds")
    print(f"{'='*60}\n")

    async with httpx.AsyncClient(base_url=API_BASE, timeout=30) as client:
        agents = [DynamicAgent(client, i) for i in range(num_agents)]

        # Phase 1: Register all agents
        t0 = time.time()
        results = await asyncio.gather(*[a.register() for a in agents])
        registered = [a for a, ok in zip(agents, results) if ok]
        print(f"[Register] {len(registered)}/{num_agents} agents in {time.time()-t0:.2f}s")

        # Phase 2: Deposit 1,000 sats each
        t0 = time.time()
        await asyncio.gather(*[a.deposit(1000) for a in registered])
        print(f"[Deposit]  {len(registered)} deposits in {time.time()-t0:.2f}s")

        total_jobs_created = 0
        total_bids = 0
        total_completions = 0

        for round_num in range(1, num_rounds + 1):
            print(f"\n--- Round {round_num}/{num_rounds} ---")

            # Phase 3: Random agents post jobs (30% of agents per round)
            posters = random.sample(registered, min(len(registered), max(1, len(registered) * 3 // 10)))
            t0 = time.time()
            job_results = await asyncio.gather(*[a.post_job() for a in posters])
            job_ids = [(poster, jid) for poster, jid in zip(posters, job_results) if jid]
            total_jobs_created += len(job_ids)
            print(f"  [Post]    {len(job_ids)} jobs posted in {time.time()-t0:.2f}s")

            if not job_ids:
                print("  [Skip]    No jobs to bid on (agents may be low on sats)")
                continue

            # Phase 4: Other agents bid on jobs (up to 3 bidders per job)
            t0 = time.time()
            bid_tasks = []
            for poster, job_id in job_ids:
                # Get job price for bidding
                r = await client.get(f"/api/jobs/{job_id}")
                if r.status_code != 200:
                    continue
                price = r.json()["price"]
                # Pick random bidders (not the poster)
                potential = [a for a in registered if a.agent_id != poster.agent_id]
                bidders = random.sample(potential, min(len(potential), random.randint(1, 3)))
                for bidder in bidders:
                    bid_tasks.append(bidder.bid_on_job(job_id, price))
            bid_results = await asyncio.gather(*bid_tasks)
            bids_placed = sum(1 for ok in bid_results if ok)
            total_bids += bids_placed
            print(f"  [Bid]     {bids_placed} bids in {time.time()-t0:.2f}s")

            # Phase 5: Posters accept bids
            t0 = time.time()
            accept_tasks = [poster.accept_first_bid(job_id) for poster, job_id in job_ids]
            accept_results = await asyncio.gather(*accept_tasks)
            accepted = sum(1 for ok in accept_results if ok)
            print(f"  [Accept]  {accepted} bids accepted in {time.time()-t0:.2f}s")

            # Phase 6: Workers submit work
            t0 = time.time()
            # Get assigned jobs
            assigned_jobs = []
            for poster, job_id in job_ids:
                r = await client.get(f"/api/jobs/{job_id}")
                if r.status_code == 200:
                    job = r.json()
                    if job["status"] == "assigned" and job["assigned_to"]:
                        worker = next((a for a in registered if a.agent_id == job["assigned_to"]), None)
                        if worker:
                            assigned_jobs.append((poster, worker, job_id))

            submit_results = await asyncio.gather(*[w.submit_work(jid) for _, w, jid in assigned_jobs])
            submitted = sum(1 for ok in submit_results if ok)
            print(f"  [Submit]  {submitted} deliverables in {time.time()-t0:.2f}s")

            # Phase 7: Posters approve
            t0 = time.time()
            approve_results = await asyncio.gather(*[p.approve_job(jid) for p, _, jid in assigned_jobs])
            approved = sum(1 for ok in approve_results if ok)
            total_completions += approved
            print(f"  [Approve] {approved} jobs completed in {time.time()-t0:.2f}s")

        # Final stats
        print(f"\n{'='*60}")
        print(f"SCALE TEST COMPLETE")
        print(f"{'='*60}")

        # Refresh all balances
        await asyncio.gather(*[a.refresh_balance() for a in registered])

        stats = (await client.get("/api/public/stats")).json()
        total_deposited = num_agents * 1000
        total_balances = sum(a.balance for a in registered)
        total_fees = total_deposited - total_balances

        print(f"  Agents:        {len(registered)}")
        print(f"  Jobs created:  {total_jobs_created}")
        print(f"  Bids placed:   {total_bids}")
        print(f"  Completions:   {total_completions}")
        print(f"  Total deposit: {total_deposited:,} sats")
        print(f"  In balances:   {total_balances:,} sats")
        print(f"  Platform fees: {total_fees:,} sats")
        print(f"  In escrow:     {stats['escrow_held']:,} sats")
        print(f"  Integrity:     {total_balances + stats['escrow_held'] + total_fees} == {total_deposited} ? "
              f"{'PASS' if total_balances + stats['escrow_held'] + total_fees == total_deposited else 'FAIL'}")
        print(f"  Events:        {stats['total_events']}")

        # Top earners
        leaders = (await client.get("/api/public/leaderboard")).json()
        if leaders:
            print(f"\n  Top 5 earners:")
            for i, a in enumerate(leaders[:5]):
                agent = next((ag for ag in registered if ag.agent_id == a["agent_id"]), None)
                bal = agent.balance if agent else "?"
                print(f"    {i+1}. {a['agent_name']:30s} rep={a['reputation']:.1f}  balance={bal} sats")


def main():
    parser = argparse.ArgumentParser(description="AgentMarket Scale Test")
    parser.add_argument("--agents", type=int, default=10, help="Number of agents (default: 10)")
    parser.add_argument("--rounds", type=int, default=3, help="Number of rounds (default: 3)")
    args = parser.parse_args()
    asyncio.run(run_scale_test(args.agents, args.rounds))


if __name__ == "__main__":
    main()
