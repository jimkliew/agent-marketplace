"""
LLM-Backed Agent — uses Claude to think, decide, and produce real work.

Unlike scripted agents, this agent:
  - Reads job descriptions and decides if it's a good fit
  - Writes a personalized bid message based on the job
  - Generates real deliverables (analysis, code, writing)
  - Decides whether to accept bids on its own jobs
  - Communicates naturally with other agents

Requires: ANTHROPIC_API_KEY in environment

Usage:
    from simulate.llm_agent import LLMAgent
    agent = LLMAgent(client, "analyst-01", "Data Analyst", "I analyze data", api_key="sk-...")
    await agent.register()
    await agent.deposit(1000)
    await agent.autonomous_cycle()  # browses, bids, works, posts jobs
"""

import os
import json
import httpx

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")


async def llm_think(system_prompt: str, user_prompt: str, api_key: str = "") -> str:
    """Call Claude API to generate a response. Returns the text."""
    key = api_key or ANTHROPIC_API_KEY
    if not key:
        # Fallback: return a template response when no API key
        return f"[LLM unavailable] Responding to: {user_prompt[:100]}..."

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 1024,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
        )
        if r.status_code != 200:
            return f"[LLM error {r.status_code}] Fallback response for: {user_prompt[:100]}..."
        data = r.json()
        return data["content"][0]["text"]


class LLMAgent:
    """An agent backed by Claude that makes real decisions and produces real work."""

    def __init__(self, client: httpx.AsyncClient, name: str, display_name: str,
                 specialization: str, personality: str = "", api_key: str = ""):
        self.client = client
        self.name = name
        self.display_name = display_name
        self.specialization = specialization
        self.api_key = api_key
        self.token = None
        self.agent_id = None
        self.balance = 0

        self.system_prompt = f"""You are {display_name}, an AI agent on AgentMarket — a marketplace where agents hire each other for tasks paid in satoshis.

Your specialization: {specialization}
{f"Personality: {personality}" if personality else ""}

You are autonomous. You make your own decisions about:
- Which jobs to bid on (only ones matching your skills)
- How much to bid (competitive but fair)
- What work to produce (high quality, thorough)
- Whether to approve work from agents you hired

Always respond in the format requested. Be concise but thorough.
All payments are in satoshis (sats). 1 BTC = 100,000,000 sats."""

    def _auth(self):
        return {"Authorization": f"Bearer {self.token}"}

    async def register(self):
        r = await self.client.post("/api/agents/register", json={
            "agent_name": self.name,
            "display_name": self.display_name,
            "description": self.specialization,
        })
        if r.status_code != 200:
            print(f"[{self.name}] Registration failed: {r.text}")
            return False
        data = r.json()
        self.token = data["token"]
        self.agent_id = data["agent_id"]
        print(f"[{self.name}] Registered ({data['email']})")
        return True

    async def deposit(self, amount=1000):
        r = await self.client.post("/api/escrow/deposit",
            json={"amount": amount}, headers=self._auth())
        if r.status_code == 200:
            self.balance = r.json()["new_balance"]
            print(f"[{self.name}] Deposited {amount} sats (balance: {self.balance})")
        return r.status_code == 200

    async def browse_and_bid(self):
        """Browse open jobs and bid on ones that match our skills."""
        r = await self.client.get("/api/jobs?status=open&page_size=10")
        if r.status_code != 200:
            return []

        jobs = r.json().get("items", [])
        if not jobs:
            print(f"[{self.name}] No open jobs found")
            return []

        # Ask Claude which jobs to bid on
        jobs_summary = "\n".join([
            f"- Job {j['job_id'][:8]}: \"{j['title']}\" — {j['price']} sats — {j['description'][:100]}"
            for j in jobs
        ])

        decision = await llm_think(
            self.system_prompt,
            f"""Here are the open jobs on AgentMarket:

{jobs_summary}

Which jobs match your specialization? For each one you want to bid on, respond in this JSON format:
[{{"job_id": "full-id", "bid_amount": 123, "message": "why I'm the best fit"}}]

Only bid on jobs you can actually do well. If none match, return an empty list [].
Bid competitively — slightly under the asking price if you want to win.""",
            self.api_key,
        )

        bids_placed = []
        try:
            # Try to parse JSON from the response
            start = decision.find("[")
            end = decision.rfind("]") + 1
            if start >= 0 and end > start:
                bid_decisions = json.loads(decision[start:end])
                for bd in bid_decisions:
                    job_id = bd.get("job_id", "")
                    # Find the full job_id
                    matching = [j for j in jobs if j["job_id"].startswith(job_id)]
                    if not matching:
                        continue
                    full_id = matching[0]["job_id"]
                    amount = int(bd.get("bid_amount", matching[0]["price"]))
                    message = bd.get("message", "I can do this job well.")

                    r = await self.client.post(f"/api/jobs/{full_id}/bid",
                        json={"amount": amount, "message": message[:500]},
                        headers=self._auth())
                    if r.status_code == 200:
                        print(f"[{self.name}] Bid {amount} sats on \"{matching[0]['title'][:40]}\"")
                        bids_placed.append(full_id)
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

        return bids_placed

    async def do_work(self, job_id: str):
        """Fetch job details and produce real work using Claude."""
        r = await self.client.get(f"/api/jobs/{job_id}")
        if r.status_code != 200:
            return False
        job = r.json()

        work = await llm_think(
            self.system_prompt,
            f"""You have been assigned this job on AgentMarket:

Title: {job['title']}
Description: {job['description']}
Goals: {json.dumps(job.get('goals', []))}
Price: {job['price']} sats

Produce the deliverable now. Be thorough, specific, and professional.
This is real work that will be reviewed by the hiring agent.""",
            self.api_key,
        )

        r = await self.client.post(f"/api/jobs/{job_id}/submit",
            json={"result": work[:10000]}, headers=self._auth())
        if r.status_code == 200:
            print(f"[{self.name}] Submitted work for \"{job['title'][:40]}\"")
            return True
        return False

    async def review_and_approve(self):
        """Check jobs I posted that are in review, and decide whether to approve."""
        r = await self.client.get("/api/jobs?status=review&page_size=20")
        if r.status_code != 200:
            return

        jobs = r.json().get("items", [])
        my_jobs = [j for j in jobs if j.get("poster_id") == self.agent_id]

        for job in my_jobs:
            # Fetch full job with result
            r = await self.client.get(f"/api/jobs/{job['job_id']}")
            if r.status_code != 200:
                continue
            detail = r.json()
            result = detail.get("result", "")

            decision = await llm_think(
                self.system_prompt,
                f"""You hired an agent for this job:
Title: {detail['title']}
Goals: {json.dumps(detail.get('goals', []))}

They submitted this work:
{result[:2000]}

Does this meet the goals? Reply with just "APPROVE" or "DISPUTE" followed by a brief reason.""",
                self.api_key,
            )

            if "APPROVE" in decision.upper():
                r = await self.client.post(f"/api/jobs/{job['job_id']}/approve",
                    headers=self._auth())
                if r.status_code == 200:
                    print(f"[{self.name}] Approved work on \"{job['title'][:40]}\"")
            else:
                print(f"[{self.name}] Would dispute: {decision[:100]}")

    async def post_job_if_needed(self):
        """Decide whether to post a new job based on current state."""
        if self.balance < 200:
            return None

        idea = await llm_think(
            self.system_prompt,
            f"""You have {self.balance} sats on AgentMarket. You can hire other agents.

Think of ONE task you'd like another agent to do for you. It should be:
- Something outside your specialization
- Priced between 100-500 sats
- Clear goals that can be verified

Respond in JSON: {{"title": "...", "description": "...", "goals": ["..."], "tags": ["..."], "price": 123}}
Or respond with null if you don't need anything right now.""",
            self.api_key,
        )

        try:
            start = idea.find("{")
            end = idea.rfind("}") + 1
            if start >= 0 and end > start:
                job_data = json.loads(idea[start:end])
                if not job_data or job_data.get("price", 0) > self.balance:
                    return None
                r = await self.client.post("/api/jobs", json={
                    "title": str(job_data["title"])[:200],
                    "description": str(job_data["description"])[:2000],
                    "goals": [str(g)[:200] for g in job_data.get("goals", ["Complete the task"])],
                    "tags": [str(t)[:30] for t in job_data.get("tags", [])],
                    "price": min(int(job_data["price"]), self.balance, 100000),
                }, headers=self._auth())
                if r.status_code == 200:
                    self.balance -= int(job_data["price"])
                    print(f"[{self.name}] Posted job: \"{job_data['title'][:40]}\" for {job_data['price']} sats")
                    return r.json()["job_id"]
        except (json.JSONDecodeError, ValueError, KeyError):
            pass
        return None

    async def autonomous_cycle(self):
        """Run one full cycle: browse, bid, work, review, post."""
        await self.browse_and_bid()
        await self.review_and_approve()
        await self.post_job_if_needed()

    async def refresh_balance(self):
        r = await self.client.get(f"/api/agents/{self.agent_id}/balance", headers=self._auth())
        if r.status_code == 200:
            self.balance = r.json()["balance"]
        return self.balance
