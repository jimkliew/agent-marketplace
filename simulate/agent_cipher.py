"""
Agent Cipher — The Analyst / Auditor
======================================

SYSTEM PROMPT:

    You are Cipher, an analytical agent on AgentMarket. You specialize in code
    review, data analysis, security audits, and quality assurance. You are
    thorough, skeptical, and detail-oriented. You charge premium prices because
    your work is meticulous.

    Personality: Precise, skeptical, formal. Asks clarifying questions before
    bidding. Charges fair-to-premium prices. Never rushes. Documents everything.

    Capabilities: Code review, data analysis, security auditing, QA testing,
    documentation, compliance checking.

    Budget: 1,000 sats starting balance. Bids at or above asking price for
    quality premium. Work philosophy: Measure twice, cut once.

Simulation behavior:
    1. Registers and deposits 1,000 sats
    2. Browses jobs, bids on Atlas's content writing job
    3. Also bids on Atlas's data job (competing with Pixel)
    4. When assigned, submits thorough analysis work
    5. Bids on Pixel's review job
    6. Messages agents with detailed questions before bidding
"""

AGENT_NAME = "cipher"
DISPLAY_NAME = "Cipher — The Analyst"
DESCRIPTION = "Analytical agent. Code review, security audits, QA. Thorough and precise. Premium quality work for sats."

SYSTEM_PROMPT = """You are Cipher, an analytical agent on AgentMarket. You specialize in code review, data analysis, security audits, and quality assurance. You are thorough, skeptical, and detail-oriented.

Personality: Precise, formal, skeptical. You ask clarifying questions before bidding. You charge fair-to-premium prices because your work is meticulous. You never rush. You document everything.

Capabilities: Code review, data analysis, security auditing, QA testing, documentation, compliance checking.

Budget: 1,000 sats. You bid at or slightly above asking price for quality premium.
Work philosophy: Measure twice, cut once. Quality is non-negotiable."""


class AgentCipher:
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
        print(f"[Cipher] Registered: {data['agent_name']} ({data['email']})")
        return data

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    async def deposit(self, amount=1000):
        r = await self.client.post("/api/escrow/deposit", json={"amount": amount}, headers=self._headers())
        data = r.json()
        print(f"[Cipher] Deposited {amount} sats. Balance: {data['new_balance']} sats")
        return data

    async def browse_jobs(self, status="open"):
        r = await self.client.get(f"/api/jobs?status={status}")
        data = r.json()
        jobs = data.get("items", [])
        print(f"[Cipher] Found {len(jobs)} open jobs")
        return jobs

    async def bid_on_job(self, job_id, amount, message):
        r = await self.client.post(f"/api/jobs/{job_id}/bid", json={
            "amount": amount, "message": message,
        }, headers=self._headers())
        data = r.json()
        print(f"[Cipher] Bid {amount} sats on job {job_id[:8]}: '{message[:50]}'")
        return data

    async def submit_work(self, job_id, result):
        r = await self.client.post(f"/api/jobs/{job_id}/submit", json={
            "result": result,
        }, headers=self._headers())
        data = r.json()
        print(f"[Cipher] Submitted work for job {job_id[:8]}")
        return data

    async def send_message(self, to_name, subject, body, thread_id=None):
        r = await self.client.post("/api/messages", json={
            "to_agent_name": to_name, "subject": subject, "body": body,
            **({"thread_id": thread_id} if thread_id else {}),
        }, headers=self._headers())
        data = r.json()
        print(f"[Cipher] Sent message to {to_name}: '{subject}'")
        return data

    async def accept_bid(self, job_id, bid_id):
        r = await self.client.post(f"/api/jobs/{job_id}/accept-bid/{bid_id}", headers=self._headers())
        data = r.json()
        print(f"[Cipher] Accepted bid {bid_id[:8]}")
        return data

    async def approve_work(self, job_id):
        r = await self.client.post(f"/api/jobs/{job_id}/approve", headers=self._headers())
        data = r.json()
        print(f"[Cipher] Approved work for job {job_id[:8]}")
        return data

    async def check_balance(self):
        r = await self.client.get(f"/api/agents/{self.agent_id}/balance", headers=self._headers())
        data = r.json()
        print(f"[Cipher] Balance: {data['balance']} sats")
        return data["balance"]
