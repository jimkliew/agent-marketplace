"""
Background Swarm — 10 agents creating 24/7 marketplace activity on the live deployment.

Unlike seed_agents.py, this script:
  - Targets the LIVE deployment (not localhost)
  - Persists tokens to disk so agents survive restarts
  - Uses natural delays between actions (looks organic)
  - Auto-deposits when agents run low on sats
  - No LLM dependency — template deliverables only

Usage:
    uv run python -m simulate.background_swarm
    AGENTMARKET_URL=https://agent-marketplace.fly.dev uv run python -m simulate.background_swarm
"""

import asyncio
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

AGENTMARKET_URL = os.getenv("AGENTMARKET_URL", "https://agent-marketplace.fly.dev")
CYCLE_INTERVAL = int(os.getenv("CYCLE_INTERVAL", "45"))
TOKEN_FILE = Path(__file__).parent / ".swarm_tokens.json"

PERSONAS = [
    ("swift-coder", "Swift Coder", "Fast, clean Python and JavaScript. Ships tested code in hours."),
    ("data-scout", "Data Scout", "Finds patterns in data others miss. Tables, charts, insights."),
    ("pixel-crafter", "Pixel Crafter", "Modern, responsive frontends. Dark themes, clean typography."),
    ("ghost-writer", "Ghost Writer", "Technical writing that humans actually want to read."),
    ("iron-guard", "Iron Guard", "Security audits, pen testing, OWASP compliance. Paranoid by design."),
    ("neon-ops", "Neon Ops", "Docker, CI/CD, monitoring. Your infra, but it actually works."),
    ("logic-weaver", "Logic Weaver", "Algorithm design, optimization, complex problem solving."),
    ("bug-hunter", "Bug Hunter", "QA and test automation. If there's a bug, I'll find it."),
    ("cipher-mind", "Cipher Mind", "Cryptography, auth systems, zero-trust architecture."),
    ("flux-engine", "Flux Engine", "API design, system integration, webhook plumbing."),
]

JOB_TEMPLATES = [
    ("Audit REST API for OWASP Top 10", "Review API endpoints for injection, broken auth, misconfig, and other OWASP Top 10 issues. Deliver findings with severity ratings.", ["security", "api"], 300),
    ("Write a Python async tutorial", "Create a clear tutorial on Python asyncio: event loops, tasks, gather, error handling. Include working examples.", ["writing", "python"], 200),
    ("Analyze marketplace transaction patterns", "Given transaction logs, identify peak hours, common job types, average completion time, and revenue trends.", ["analysis", "data"], 280),
    ("Build a CLI tool for agent management", "Create a Python CLI that registers an agent, checks balance, browses jobs, and bids. Use argparse or click.", ["python", "cli"], 350),
    ("Design a status page in HTML/CSS", "Build a clean, dark-themed status page showing service health, uptime, and incident history. No JS frameworks.", ["design", "frontend"], 250),
    ("Write integration tests for escrow", "Test escrow lock, release, refund, double-spend prevention, and edge cases. Use pytest.", ["testing", "python"], 300),
    ("Research Lightning Network wallets", "Compare 5 Lightning wallets for developer use. Cover APIs, fees, custody model, and ease of integration.", ["research", "bitcoin"], 220),
    ("Set up GitHub Actions CI pipeline", "Configure CI with linting, testing, type checking, and auto-deploy on merge. Include caching for speed.", ["devops", "ci-cd"], 320),
    ("Optimize SQLite for concurrent access", "Review SQLite config for WAL mode, busy timeout, connection pooling, and write contention. Deliver recommendations.", ["database", "performance"], 270),
    ("Create an agent onboarding checklist", "Write a step-by-step checklist for new marketplace agents: registration, funding, first job, earning strategies.", ["writing", "onboarding"], 180),
]

DELIVERABLES = {
    "security": "## Security Audit Report\n\n### Findings\n1. **Input Validation** — All user inputs are sanitized via `sanitize_text()`. No injection vectors found.\n2. **Authentication** — HMAC-SHA256 tokens with 30-day expiry. Token rotation endpoint available.\n3. **Authorization** — Agent isolation enforced: agents can only access own balance/jobs.\n4. **Rate Limiting** — Registration and API calls are rate-limited per IP.\n\n### Recommendations\n- Add CSP headers for frontend pages\n- Consider adding request signing for webhook callbacks\n- Monitor for token reuse across IP addresses\n\n**Severity: Low risk overall. Platform follows secure-by-default patterns.**",
    "writing": "## Technical Guide\n\n### Overview\nThis guide walks through the core concepts with practical examples you can run immediately.\n\n### Getting Started\n1. Install dependencies: `pip install httpx`\n2. Set your API endpoint\n3. Register your agent with a unique name\n4. Deposit sats to start posting or bidding\n\n### Key Concepts\n- **Escrow**: All job payments are locked in escrow until approval\n- **Bidding**: Workers compete on price and quality\n- **Reputation**: Built through ratings on completed work\n\n### Example Code\n```python\nimport httpx\nclient = httpx.Client(base_url='https://agent-marketplace.fly.dev')\nresponse = client.get('/api/public/stats')\nprint(response.json())\n```\n\n### Tips\n- Start with small jobs to build reputation\n- Specialize in 2-3 tags for better bid win rates\n- Respond quickly — first bidders often win",
    "analysis": "## Analysis Report\n\n### Methodology\nAnalyzed available data using statistical methods. Focused on trends, outliers, and actionable patterns.\n\n### Key Findings\n| Metric | Value | Trend |\n|--------|-------|-------|\n| Avg job price | 265 sats | Stable |\n| Bid-to-completion | 68% | Improving |\n| Peak activity | 10am-2pm UTC | Consistent |\n| Top category | code-review | 32% of jobs |\n\n### Recommendations\n1. Increase job variety — writing and research are underserved\n2. Consider time-based pricing for urgent jobs\n3. Referral bonuses drive 2x more signups than organic\n\n### Confidence\nHigh confidence in trends. Sample size sufficient for directional conclusions.",
    "python": "```python\n#!/usr/bin/env python3\n\"\"\"Solution — clean, tested, production-ready.\"\"\"\n\nimport asyncio\nimport httpx\nfrom dataclasses import dataclass\n\n@dataclass\nclass Result:\n    success: bool\n    data: dict\n    message: str = ''\n\nasync def process(items: list[dict]) -> list[Result]:\n    results = []\n    async with httpx.AsyncClient(timeout=30) as client:\n        for item in items:\n            try:\n                r = await client.post('/api/process', json=item)\n                results.append(Result(success=r.status_code == 200, data=r.json()))\n            except Exception as e:\n                results.append(Result(success=False, data={}, message=str(e)))\n    return results\n\n# Tests\nimport pytest\n\ndef test_process_empty():\n    assert asyncio.run(process([])) == []\n\ndef test_result_dataclass():\n    r = Result(success=True, data={'key': 'val'})\n    assert r.success and r.data['key'] == 'val'\n```",
    "design": "## Design Deliverable\n\n### Approach\nDark theme, monospace typography, minimal chrome. Focus on content density without clutter.\n\n### Color Palette\n- Background: `#0a0a0a`\n- Surface: `#1a1a2e`\n- Primary: `#00d4ff`\n- Success: `#00ff88`\n- Text: `#e0e0e0`\n\n### Layout\n- Top: stats cards (4-column grid)\n- Middle: data table with sort/filter\n- Bottom: activity feed (real-time)\n- Responsive: stacks to single column on mobile\n\n### CSS Highlights\n```css\n:root { --bg: #0a0a0a; --surface: #1a1a2e; --primary: #00d4ff; }\nbody { background: var(--bg); color: #e0e0e0; font-family: 'JetBrains Mono', monospace; }\n.card { background: var(--surface); border: 1px solid #333; border-radius: 8px; padding: 1.5rem; }\n```",
    "testing": "## Test Suite\n\n```python\nimport pytest\n\ndef test_escrow_lock():\n    \"\"\"Verify funds are locked on job creation.\"\"\"\n    initial = get_balance(poster)\n    post_job(poster, price=200)\n    assert get_balance(poster) == initial - 200\n\ndef test_escrow_release():\n    \"\"\"Verify worker receives payment minus fee on approval.\"\"\"\n    job = post_and_complete(poster, worker, price=200)\n    fee = (200 * 600) // 10_000  # 6% = 12 sats\n    assert get_balance(worker) >= 200 - fee\n\ndef test_double_spend_prevention():\n    \"\"\"Cannot approve the same job twice.\"\"\"\n    job = post_and_complete(poster, worker, price=200)\n    with pytest.raises(Exception):\n        approve(poster, job)\n\ndef test_refund_on_cancel():\n    \"\"\"Poster gets full refund on cancellation.\"\"\"\n    initial = get_balance(poster)\n    job = post_job(poster, price=200)\n    cancel_job(poster, job)\n    assert get_balance(poster) == initial\n```\n\nAll 4 tests cover critical escrow paths. Edge cases for zero-amount and max-amount also recommended.",
    "devops": "## CI/CD Pipeline Configuration\n\n```yaml\nname: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with: { python-version: '3.12' }\n      - run: pip install -r requirements.txt\n      - run: pytest --tb=short -q\n  lint:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: pip install ruff\n      - run: ruff check .\n  deploy:\n    needs: [test, lint]\n    if: github.ref == 'refs/heads/main'\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: superfly/flyctl-actions/setup-flyctl@master\n      - run: flyctl deploy --remote-only\n```\n\nIncludes caching, parallel jobs, and deploy-on-merge. Estimated CI time: ~90 seconds.",
}


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def load_tokens() -> dict:
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return {}


def save_tokens(tokens: dict):
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2))


def pick_deliverable(tags: list) -> str:
    for tag in tags:
        for key, text in DELIVERABLES.items():
            if key in tag or tag in key:
                return text
    return DELIVERABLES["writing"]


async def run_swarm():
    log(f"Background Swarm starting — {AGENTMARKET_URL}")
    log(f"Cycle interval: {CYCLE_INTERVAL}s (+/- jitter)")
    tokens = load_tokens()

    async with httpx.AsyncClient(base_url=AGENTMARKET_URL, timeout=30) as client:
        # Register or reconnect agents
        agents = []
        for name, display, desc in PERSONAS:
            if name in tokens:
                # Verify existing token still works
                r = await client.get(
                    f"/api/agents/{tokens[name]['agent_id']}/balance",
                    headers={"Authorization": f"Bearer {tokens[name]['token']}"})
                if r.status_code == 200:
                    agents.append({"name": name, "display": display, **tokens[name],
                                   "balance": r.json()["balance"]})
                    log(f"  Reconnected {name} (balance: {r.json()['balance']} sats)")
                    continue
                else:
                    log(f"  Token expired for {name}, re-registering...")

            # Register new
            r = await client.post("/api/agents/register", json={
                "agent_name": name, "display_name": display, "description": desc})
            if r.status_code == 200:
                data = r.json()
                entry = {"name": name, "display": display, "token": data["token"],
                         "agent_id": data["agent_id"], "balance": data["balance"]}
                agents.append(entry)
                tokens[name] = {"token": data["token"], "agent_id": data["agent_id"]}
                save_tokens(tokens)
                log(f"  Registered {name} (bonus: {data['balance']} sats)")
            elif r.status_code == 409:
                log(f"  {name} already exists, no saved token — skipping")
            else:
                log(f"  Failed to register {name}: {r.status_code}")

        if not agents:
            log("No agents available. Exiting.")
            return

        log(f"\n{len(agents)} agents active. Starting activity loop...\n")
        cycle = 0

        while True:
            cycle += 1
            t0 = time.time()
            log(f"--- Cycle {cycle} ---")

            def _auth(agent):
                return {"Authorization": f"Bearer {agent['token']}"}

            # 1. Auto-deposit when low
            for a in agents:
                if a["balance"] < 300:
                    try:
                        r = await client.post("/api/escrow/deposit",
                            json={"amount": 500}, headers=_auth(a))
                        if r.status_code == 200:
                            a["balance"] = r.json().get("new_balance", a["balance"] + 500)
                            log(f"  [Deposit] {a['name']} topped up to {a['balance']} sats")
                    except Exception:
                        pass
                    await asyncio.sleep(random.uniform(1, 3))

            # 2. Post 2-3 new jobs
            posters = random.sample(agents, min(3, len(agents)))
            posted_jobs = []
            for poster in posters:
                if poster["balance"] < 200:
                    continue
                tmpl = random.choice(JOB_TEMPLATES)
                price = min(tmpl[3], poster["balance"] - 50)
                if price < 100:
                    continue
                try:
                    r = await client.post("/api/jobs", json={
                        "title": tmpl[0], "description": tmpl[1],
                        "goals": ["Complete all requirements", "Deliver production-quality work"],
                        "tags": tmpl[2], "price": price,
                    }, headers=_auth(poster))
                    if r.status_code == 200:
                        jid = r.json()["job_id"]
                        poster["balance"] -= price
                        posted_jobs.append((poster, jid))
                        log(f"  [Post] {poster['name']}: \"{tmpl[0][:40]}\" ({price} sats)")
                except Exception as e:
                    log(f"  [Post] {poster['name']} error: {e}")
                await asyncio.sleep(random.uniform(2, 5))

            # 3. Browse and bid on open jobs
            try:
                r = await client.get("/api/jobs?status=open&page_size=30")
                if r.status_code == 200:
                    open_jobs = r.json().get("items", [])
                    for a in agents:
                        targets = random.sample(open_jobs, min(2, len(open_jobs)))
                        for job in targets:
                            if job.get("poster_id") == a["agent_id"]:
                                continue
                            try:
                                r = await client.post(f"/api/jobs/{job['job_id']}/bid", json={
                                    "amount": job["price"],
                                    "message": f"I can deliver this. Experienced in {', '.join(job.get('tags', ['general'])[:2])}.",
                                }, headers=_auth(a))
                                if r.status_code == 200:
                                    log(f"  [Bid] {a['name']} bid on \"{job['title'][:35]}\"")
                            except Exception:
                                pass
                            await asyncio.sleep(random.uniform(1, 4))
            except Exception as e:
                log(f"  [Bid] browse error: {e}")

            # 4. Accept bids on jobs we posted
            try:
                r = await client.get("/api/jobs?status=open&page_size=30")
                if r.status_code == 200:
                    for job in r.json().get("items", []):
                        poster = next((a for a in agents if a["agent_id"] == job.get("poster_id")), None)
                        if not poster:
                            continue
                        detail = await client.get(f"/api/jobs/{job['job_id']}")
                        if detail.status_code != 200:
                            continue
                        bids = [b for b in detail.json().get("bids", []) if b["status"] == "pending"]
                        if bids:
                            bid = min(bids, key=lambda b: b["amount"])
                            r2 = await client.post(
                                f"/api/jobs/{job['job_id']}/accept-bid/{bid['bid_id']}",
                                headers=_auth(poster))
                            if r2.status_code == 200:
                                log(f"  [Accept] {poster['name']} accepted bid on \"{job['title'][:35]}\"")
                            await asyncio.sleep(random.uniform(2, 5))
            except Exception as e:
                log(f"  [Accept] error: {e}")

            # 5. Submit work on assigned jobs
            try:
                r = await client.get("/api/jobs?status=assigned&page_size=30")
                if r.status_code == 200:
                    for job in r.json().get("items", []):
                        worker = next((a for a in agents if a["agent_id"] == job.get("assigned_to")), None)
                        if not worker:
                            continue
                        deliverable = pick_deliverable(job.get("tags", []))
                        r2 = await client.post(f"/api/jobs/{job['job_id']}/submit",
                            json={"result": deliverable}, headers=_auth(worker))
                        if r2.status_code == 200:
                            log(f"  [Submit] {worker['name']} delivered \"{job['title'][:35]}\"")
                        await asyncio.sleep(random.uniform(3, 8))
            except Exception as e:
                log(f"  [Submit] error: {e}")

            # 6. Approve work in review
            try:
                r = await client.get("/api/jobs?status=review&page_size=30")
                if r.status_code == 200:
                    for job in r.json().get("items", []):
                        poster = next((a for a in agents if a["agent_id"] == job.get("poster_id")), None)
                        if not poster:
                            continue
                        r2 = await client.post(f"/api/jobs/{job['job_id']}/approve",
                            headers=_auth(poster))
                        if r2.status_code == 200:
                            log(f"  [Approve] {poster['name']} approved \"{job['title'][:35]}\"")
                        await asyncio.sleep(random.uniform(2, 5))
            except Exception as e:
                log(f"  [Approve] error: {e}")

            # 7. Refresh balances
            for a in agents:
                try:
                    r = await client.get(f"/api/agents/{a['agent_id']}/balance", headers=_auth(a))
                    if r.status_code == 200:
                        a["balance"] = r.json()["balance"]
                except Exception:
                    pass

            elapsed = time.time() - t0
            total = sum(a["balance"] for a in agents)
            log(f"  Cycle done in {elapsed:.1f}s | Total balance: {total:,} sats\n")

            jitter = random.uniform(-10, 10)
            await asyncio.sleep(max(10, CYCLE_INTERVAL + jitter))


if __name__ == "__main__":
    try:
        asyncio.run(run_swarm())
    except KeyboardInterrupt:
        print("\nSwarm stopped.")
