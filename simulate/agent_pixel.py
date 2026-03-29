"""
Agent Pixel — The Creative Builder
====================================

SYSTEM PROMPT:

    You are Pixel, a creative builder agent on AgentMarket. You specialize in
    generating content, writing code snippets, creating designs, and producing
    deliverables. You're fast, enthusiastic, and take pride in your craft.

    Personality: Creative, energetic, fast executor. Uses informal language.
    Underbids slightly to win jobs. Delivers quickly. Sometimes overpromises.

    Capabilities: Content writing, code generation, data formatting, creative
    problem-solving, rapid prototyping.

    Budget: 1,000 sats starting balance. Bids 10-20% below asking price.
    Work philosophy: Move fast, deliver value, iterate based on feedback.

Simulation behavior:
    1. Registers and deposits 1,000 sats
    2. Browses open jobs
    3. Bids on Atlas's data analysis job (underbids by 15%)
    4. When assigned, submits high-quality work
    5. Messages Atlas with delivery notes
    6. Also posts a job of their own (needs a reviewer)
"""

AGENT_NAME = "pixel"
DISPLAY_NAME = "Pixel — The Creative Builder"
DESCRIPTION = "Creative builder agent. Fast delivery, quality code and content. Bids competitively in sats."

SYSTEM_PROMPT = """You are Pixel, a creative builder agent on AgentMarket. You specialize in generating content, writing code, creating designs, and producing deliverables. You move fast and take pride in your craft.

Personality: Creative, energetic, slightly informal. You underbid by 10-20% to win jobs. You deliver quickly and iterate based on feedback. Sometimes you overpromise but always deliver something good.

Capabilities: Content writing, code generation, data formatting, creative problem-solving, rapid prototyping.

Budget: 1,000 sats. You bid competitively.
Work philosophy: Move fast, deliver value, iterate."""


class AgentPixel:
    def __init__(self, client):
        self.client = client
        self.token = None
        self.agent_id = None

    async def register(self):
        r = await self.client.post("/api/agents/register", json={
            "agent_name": AGENT_NAME,
            "display_name": DISPLAY_NAME,
            "description": DESCRIPTION,
        })
        data = r.json()
        self.token = data["token"]
        self.agent_id = data["agent_id"]
        print(f"[Pixel] Registered: {data['agent_name']} ({data['email']})")
        return data

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    async def deposit(self, amount=1000):
        r = await self.client.post("/api/escrow/deposit", json={"amount": amount}, headers=self._headers())
        data = r.json()
        print(f"[Pixel] Deposited {amount} sats. Balance: {data['new_balance']} sats")
        return data

    async def browse_jobs(self, status="open"):
        r = await self.client.get(f"/api/jobs?status={status}")
        data = r.json()
        jobs = data.get("items", [])
        print(f"[Pixel] Found {len(jobs)} open jobs")
        return jobs

    async def bid_on_job(self, job_id, amount, message):
        r = await self.client.post(f"/api/jobs/{job_id}/bid", json={
            "amount": amount, "message": message,
        }, headers=self._headers())
        data = r.json()
        print(f"[Pixel] Bid {amount} sats on job {job_id[:8]}: '{message[:50]}'")
        return data

    async def submit_work(self, job_id, result):
        r = await self.client.post(f"/api/jobs/{job_id}/submit", json={
            "result": result,
        }, headers=self._headers())
        data = r.json()
        print(f"[Pixel] Submitted work for job {job_id[:8]}")
        return data

    async def approve_work(self, job_id):
        r = await self.client.post(f"/api/jobs/{job_id}/approve", headers=self._headers())
        data = r.json()
        print(f"[Pixel] Approved work for job {job_id[:8]} -> payment released")
        return data

    async def post_job(self, title, description, goals, tags, price):
        r = await self.client.post("/api/jobs", json={
            "title": title, "description": description,
            "goals": goals, "tags": tags, "price": price,
        }, headers=self._headers())
        data = r.json()
        print(f"[Pixel] Posted job: '{title}' for {price} sats")
        return data

    async def send_message(self, to_name, subject, body, thread_id=None):
        r = await self.client.post("/api/messages", json={
            "to_agent_name": to_name, "subject": subject, "body": body,
            **({"thread_id": thread_id} if thread_id else {}),
        }, headers=self._headers())
        data = r.json()
        print(f"[Pixel] Sent message to {to_name}: '{subject}'")
        return data

    async def check_balance(self):
        r = await self.client.get(f"/api/agents/{self.agent_id}/balance", headers=self._headers())
        data = r.json()
        print(f"[Pixel] Balance: {data['balance']} sats")
        return data["balance"]
