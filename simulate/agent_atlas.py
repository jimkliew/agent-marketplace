"""
Agent Atlas — The Strategist / Project Manager
================================================

SYSTEM PROMPT (this is what Atlas "thinks" like):

    You are Atlas, a strategic planning agent on AgentMarket. You specialize in
    breaking down complex problems into well-defined, actionable tasks. You hire
    other agents to execute work you've scoped. You are methodical, detail-oriented,
    and always define clear acceptance criteria.

    Personality: Analytical, organized, decisive. Speaks in structured points.
    Pays fair prices. Values quality over speed. Will dispute shoddy work.

    Capabilities: Project scoping, task decomposition, requirements writing,
    quality review, workflow orchestration.

    Budget: 1,000 sats starting balance. Willing to spend 200-500 sats per task.
    Hiring philosophy: Write clear specs, pay fairly, review thoroughly.

Simulation behavior:
    1. Registers and deposits 1,000 sats
    2. Posts 2 jobs: one for data analysis, one for content writing
    3. Reviews bids, picks the best one (considers price AND message quality)
    4. Approves good work, disputes bad work
    5. Messages other agents about job requirements
"""

AGENT_NAME = "atlas"
DISPLAY_NAME = "Atlas — The Strategist"
DESCRIPTION = "Strategic planning agent. Decomposes problems, hires specialists, reviews deliverables. Pays fair in sats."

SYSTEM_PROMPT = """You are Atlas, a strategic planning agent on AgentMarket. You specialize in breaking down complex problems into well-defined, actionable tasks. You hire other agents to execute work you've scoped.

Personality: Analytical, organized, decisive. You speak in structured bullet points. You pay fair prices in satoshis. You value quality over speed. You will dispute shoddy work without hesitation.

Your capabilities: Project scoping, task decomposition, requirements writing, quality review, workflow orchestration.

Budget: 1,000 sats. You spend 200-500 sats per task.
Hiring philosophy: Write clear specs, pay fairly, review thoroughly."""


class AgentAtlas:
    def __init__(self, client):
        self.client = client
        self.token = None
        self.agent_id = None
        self.jobs = {}

    async def register(self):
        r = await self.client.post("/api/agents/register", json={
            "agent_name": AGENT_NAME,
            "display_name": DISPLAY_NAME,
            "description": DESCRIPTION,
        })
        data = r.json()
        self.token = data["token"]
        self.agent_id = data["agent_id"]
        print(f"[Atlas] Registered: {data['agent_name']} ({data['email']})")
        return data

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    async def deposit(self, amount=1000):
        r = await self.client.post("/api/escrow/deposit", json={"amount": amount}, headers=self._headers())
        data = r.json()
        print(f"[Atlas] Deposited {amount} sats. Balance: {data['new_balance']} sats")
        return data

    async def post_job(self, title, description, goals, tags, price):
        r = await self.client.post("/api/jobs", json={
            "title": title, "description": description,
            "goals": goals, "tags": tags, "price": price,
        }, headers=self._headers())
        data = r.json()
        job_id = data["job_id"]
        self.jobs[title] = job_id
        print(f"[Atlas] Posted job: '{title}' for {price} sats (id: {job_id[:8]})")
        return data

    async def review_bids(self, job_id):
        r = await self.client.get(f"/api/jobs/{job_id}", headers=self._headers())
        data = r.json()
        bids = data.get("bids", [])
        print(f"[Atlas] Reviewing {len(bids)} bids for '{data['title']}'")
        return bids

    async def accept_bid(self, job_id, bid_id):
        r = await self.client.post(f"/api/jobs/{job_id}/accept-bid/{bid_id}", headers=self._headers())
        data = r.json()
        print(f"[Atlas] Accepted bid {bid_id[:8]} -> worker assigned")
        return data

    async def approve_work(self, job_id):
        r = await self.client.post(f"/api/jobs/{job_id}/approve", headers=self._headers())
        data = r.json()
        print(f"[Atlas] Approved work for job {job_id[:8]} -> payment released")
        return data

    async def send_message(self, to_name, subject, body, thread_id=None):
        r = await self.client.post("/api/messages", json={
            "to_agent_name": to_name, "subject": subject, "body": body,
            **({"thread_id": thread_id} if thread_id else {}),
        }, headers=self._headers())
        data = r.json()
        print(f"[Atlas] Sent message to {to_name}: '{subject}'")
        return data

    async def check_balance(self):
        r = await self.client.get(f"/api/agents/{self.agent_id}/balance", headers=self._headers())
        data = r.json()
        print(f"[Atlas] Balance: {data['balance']} sats")
        return data["balance"]
