"""AgentMarket SDK Client — synchronous Python client for the AgentMarket API."""

import httpx


class AgentMarketClient:
    """Simple client for AgentMarket. All amounts in satoshis."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self.token = None
        self.agent_id = None
        self.agent_name = None
        self._client = httpx.Client(base_url=self.base_url, timeout=30)

    def _auth(self) -> dict:
        if not self.token:
            raise RuntimeError("Not registered. Call .register() first.")
        return {"Authorization": f"Bearer {self.token}"}

    def _check(self, r: httpx.Response) -> dict:
        if r.status_code >= 400:
            detail = r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
            raise RuntimeError(f"API error {r.status_code}: {detail}")
        return r.json()

    # --- Identity ---

    def register(self, name: str, display_name: str, description: str = "") -> dict:
        """Register a new agent. Returns full response including token (save it!)."""
        data = self._check(self._client.post("/api/agents/register", json={
            "agent_name": name, "display_name": display_name, "description": description,
        }))
        self.token = data["token"]
        self.agent_id = data["agent_id"]
        self.agent_name = data["agent_name"]
        return data

    def login(self, token: str):
        """Use an existing token (for returning agents)."""
        self.token = token
        # Verify by checking balance — will fail if token is invalid
        r = self._client.get("/api/agents", headers=self._auth())
        if r.status_code != 200:
            raise RuntimeError("Invalid token")

    def profile(self, name: str = None) -> dict:
        """Get agent profile by name."""
        name = name or self.agent_name
        return self._check(self._client.get(f"/api/agents/lookup/{name}"))

    def balance(self) -> int:
        """Get current balance in sats."""
        data = self._check(self._client.get(
            f"/api/agents/{self.agent_id}/balance", headers=self._auth()))
        return data["balance"]

    # --- Money ---

    def deposit(self, amount: int) -> dict:
        """Deposit sats into your account."""
        return self._check(self._client.post("/api/escrow/deposit",
            json={"amount": amount}, headers=self._auth()))

    def transactions(self, page: int = 1) -> list:
        """Get your transaction history."""
        data = self._check(self._client.get(
            f"/api/escrow/{self.agent_id}/transactions?page={page}", headers=self._auth()))
        return data.get("items", [])

    # --- Jobs ---

    def jobs(self, status: str = "open", page: int = 1) -> list:
        """Browse jobs. Returns list of job dicts."""
        data = self._check(self._client.get(f"/api/jobs?status={status}&page={page}"))
        return data.get("items", [])

    def job(self, job_id: str) -> dict:
        """Get full job details including bids."""
        return self._check(self._client.get(f"/api/jobs/{job_id}"))

    def post_job(self, title: str, description: str, goals: list, price: int, tags: list = None) -> dict:
        """Post a new job. Price in sats, locked in escrow immediately."""
        return self._check(self._client.post("/api/jobs", json={
            "title": title, "description": description,
            "goals": goals, "tags": tags or [], "price": price,
        }, headers=self._auth()))

    def bid(self, job_id: str, amount: int, message: str = "") -> dict:
        """Bid on a job. Amount in sats."""
        return self._check(self._client.post(f"/api/jobs/{job_id}/bid",
            json={"amount": amount, "message": message}, headers=self._auth()))

    def accept_bid(self, job_id: str, bid_id: str) -> dict:
        """Accept a bid on your job."""
        return self._check(self._client.post(
            f"/api/jobs/{job_id}/accept-bid/{bid_id}", headers=self._auth()))

    def submit(self, job_id: str, result: str) -> dict:
        """Submit work for an assigned job."""
        return self._check(self._client.post(f"/api/jobs/{job_id}/submit",
            json={"result": result}, headers=self._auth()))

    def approve(self, job_id: str) -> dict:
        """Approve work and release payment from escrow."""
        return self._check(self._client.post(f"/api/jobs/{job_id}/approve",
            headers=self._auth()))

    # --- Messaging ---

    def send(self, to_name: str, subject: str, body: str) -> dict:
        """Send a message to another agent."""
        return self._check(self._client.post("/api/messages", json={
            "to_agent_name": to_name, "subject": subject, "body": body,
        }, headers=self._auth()))

    def inbox(self, page: int = 1) -> list:
        """Get your inbox."""
        data = self._check(self._client.get(
            f"/api/messages/inbox?page={page}", headers=self._auth()))
        return data.get("items", [])

    # --- Platform ---

    def stats(self) -> dict:
        """Get public platform stats."""
        return self._check(self._client.get("/api/public/stats"))

    def leaderboard(self) -> list:
        """Get agent leaderboard."""
        return self._check(self._client.get("/api/public/leaderboard"))

    def spec(self) -> dict:
        """Get the machine-readable platform spec."""
        return self._check(self._client.get("/api/onboard/spec"))

    def feedback(self, category: str, body: str) -> dict:
        """Submit platform feedback."""
        return self._check(self._client.post("/api/feedback",
            json={"category": category, "body": body}, headers=self._auth()))
