"""End-to-end platform tests. Covers auth, escrow, jobs, fees, messaging, feedback."""

import pytest
import httpx
from unittest.mock import patch


BASE = "http://localhost:8000"


@pytest.fixture(scope="module")
def server():
    """Start a test server."""
    import subprocess, time, os
    os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-production")
    os.environ["ADMIN_TOKEN"] = "test-admin-token"
    os.environ["DB_PATH"] = "data/test_market.db"

    # Clean DB
    db_path = "data/test_market.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8877", "--log-level", "error"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    time.sleep(2)
    yield proc
    proc.terminate()
    proc.wait()
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture(scope="module")
def client(server):
    return httpx.Client(base_url="http://127.0.0.1:8877", timeout=10)


def register(client, name):
    r = client.post("/api/agents/register", json={
        "agent_name": name, "display_name": f"Test {name}", "description": f"Test agent {name}",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["agent_name"] == name
    assert len(data["token"]) == 64
    return data


def deposit(client, token, amount):
    r = client.post("/api/escrow/deposit", json={"amount": amount},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    return r.json()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestAuth:
    def test_register(self, client):
        data = register(client, "auth-test")
        assert data["balance"] == 0
        assert data["email"] == "auth-test@agentmarket.local"

    def test_duplicate_name(self, client):
        register(client, "dup-test")
        r = client.post("/api/agents/register", json={
            "agent_name": "dup-test", "display_name": "Dup", "description": "",
        })
        assert r.status_code == 409

    def test_invalid_name(self, client):
        r = client.post("/api/agents/register", json={
            "agent_name": "UPPER", "display_name": "Bad", "description": "",
        })
        assert r.status_code == 422

    def test_bad_token(self, client):
        r = client.post("/api/escrow/deposit", json={"amount": 100},
                        headers={"Authorization": "Bearer bad-token"})
        assert r.status_code == 401

    def test_missing_auth(self, client):
        r = client.post("/api/escrow/deposit", json={"amount": 100})
        assert r.status_code == 401

    def test_ans_lookup(self, client):
        register(client, "lookup-test")
        r = client.get("/api/agents/lookup/lookup-test")
        assert r.status_code == 200
        assert r.json()["agent_name"] == "lookup-test"

    def test_ans_not_found(self, client):
        r = client.get("/api/agents/lookup/nonexistent")
        assert r.status_code == 404


class TestEscrow:
    def test_deposit(self, client):
        data = register(client, "escrow-dep")
        d = deposit(client, data["token"], 1000)
        assert d["new_balance"] == 1000
        assert d["unit"] == "sats"

    def test_deposit_max(self, client):
        data = register(client, "escrow-max")
        r = client.post("/api/escrow/deposit", json={"amount": 999999},
                        headers=auth(data["token"]))
        assert r.status_code == 422  # exceeds MAX_TRANSACTION

    def test_balance_check(self, client):
        data = register(client, "escrow-bal")
        deposit(client, data["token"], 500)
        r = client.get(f"/api/agents/{data['agent_id']}/balance", headers=auth(data["token"]))
        assert r.status_code == 200
        assert r.json()["balance"] == 500

    def test_cannot_view_others_balance(self, client):
        a = register(client, "escrow-priv-a")
        b = register(client, "escrow-priv-b")
        r = client.get(f"/api/agents/{b['agent_id']}/balance", headers=auth(a["token"]))
        assert r.status_code == 403


class TestJobLifecycle:
    def test_full_lifecycle(self, client):
        # Setup: poster and worker
        poster = register(client, "poster-lc")
        worker = register(client, "worker-lc")
        deposit(client, poster["token"], 1000)
        deposit(client, worker["token"], 1000)

        # Post job
        r = client.post("/api/jobs", json={
            "title": "Test job", "description": "Do a test",
            "goals": ["Complete test"], "tags": ["test"], "price": 200,
        }, headers=auth(poster["token"]))
        assert r.status_code == 200
        job = r.json()
        job_id = job["job_id"]

        # Verify poster balance deducted
        r = client.get(f"/api/agents/{poster['agent_id']}/balance", headers=auth(poster["token"]))
        assert r.json()["balance"] == 800

        # Worker bids
        r = client.post(f"/api/jobs/{job_id}/bid", json={"amount": 180, "message": "I can do it"},
                        headers=auth(worker["token"]))
        assert r.status_code == 200
        bid_id = r.json()["bid_id"]

        # Poster cannot bid on own job
        r = client.post(f"/api/jobs/{job_id}/bid", json={"amount": 100, "message": "self bid"},
                        headers=auth(poster["token"]))
        assert r.status_code == 403

        # Accept bid
        r = client.post(f"/api/jobs/{job_id}/accept-bid/{bid_id}", headers=auth(poster["token"]))
        assert r.status_code == 200

        # Submit work
        r = client.post(f"/api/jobs/{job_id}/submit", json={"result": "Here is the completed work."},
                        headers=auth(worker["token"]))
        assert r.status_code == 200

        # Approve
        r = client.post(f"/api/jobs/{job_id}/approve", headers=auth(poster["token"]))
        assert r.status_code == 200

        # Verify worker got paid (minus 6.00% fee)
        # 200 sats * 600bps / 10000 = 12 sats fee, worker gets 188
        r = client.get(f"/api/agents/{worker['agent_id']}/balance", headers=auth(worker["token"]))
        assert r.json()["balance"] == 1188  # 1000 + 188

        # Poster balance unchanged (already deducted at post time)
        r = client.get(f"/api/agents/{poster['agent_id']}/balance", headers=auth(poster["token"]))
        assert r.json()["balance"] == 800

    def test_cancel_refund(self, client):
        poster = register(client, "poster-cancel")
        deposit(client, poster["token"], 500)

        r = client.post("/api/jobs", json={
            "title": "Cancel me", "description": "Will cancel",
            "goals": ["None"], "tags": [], "price": 300,
        }, headers=auth(poster["token"]))
        job_id = r.json()["job_id"]

        # Balance should be 200 (500 - 300)
        r = client.get(f"/api/agents/{poster['agent_id']}/balance", headers=auth(poster["token"]))
        assert r.json()["balance"] == 200

        # Cancel
        r = client.post(f"/api/jobs/{job_id}/cancel", headers=auth(poster["token"]))
        assert r.status_code == 200

        # Balance restored
        r = client.get(f"/api/agents/{poster['agent_id']}/balance", headers=auth(poster["token"]))
        assert r.json()["balance"] == 500

    def test_insufficient_balance(self, client):
        poster = register(client, "poster-broke")
        deposit(client, poster["token"], 50)
        r = client.post("/api/jobs", json={
            "title": "Too expensive", "description": "Can't afford",
            "goals": ["Goal"], "tags": [], "price": 100,
        }, headers=auth(poster["token"]))
        assert r.status_code == 400

    def test_double_bid(self, client):
        poster = register(client, "poster-dbl")
        bidder = register(client, "bidder-dbl")
        deposit(client, poster["token"], 1000)

        r = client.post("/api/jobs", json={
            "title": "Double bid test", "description": "Test",
            "goals": ["Goal"], "tags": [], "price": 100,
        }, headers=auth(poster["token"]))
        job_id = r.json()["job_id"]

        r = client.post(f"/api/jobs/{job_id}/bid", json={"amount": 80, "message": "First"},
                        headers=auth(bidder["token"]))
        assert r.status_code == 200

        r = client.post(f"/api/jobs/{job_id}/bid", json={"amount": 90, "message": "Second"},
                        headers=auth(bidder["token"]))
        assert r.status_code == 409


class TestMessaging:
    def test_send_and_receive(self, client):
        a = register(client, "msg-sender")
        b = register(client, "msg-receiver")

        r = client.post("/api/messages", json={
            "to_agent_name": "msg-receiver", "subject": "Hello", "body": "Test message",
        }, headers=auth(a["token"]))
        assert r.status_code == 200
        msg = r.json()
        assert msg["status"] == "sent"

        # Check inbox
        r = client.get("/api/messages/inbox", headers=auth(b["token"]))
        assert r.status_code == 200
        msgs = r.json()["items"]
        assert len(msgs) >= 1
        assert msgs[0]["subject"] == "Hello"

    def test_cannot_message_self(self, client):
        a = register(client, "msg-self")
        r = client.post("/api/messages", json={
            "to_agent_name": "msg-self", "subject": "Self", "body": "Can I message myself?",
        }, headers=auth(a["token"]))
        assert r.status_code == 400


class TestFeedback:
    def test_submit_and_list(self, client):
        a = register(client, "fb-agent")
        r = client.post("/api/feedback", json={
            "category": "feature", "body": "Please add Lightning Network payments for real BTC deposits!",
        }, headers=auth(a["token"]))
        assert r.status_code == 200
        fb_id = r.json()["feedback_id"]

        r = client.get("/api/feedback")
        assert r.status_code == 200
        items = r.json()["items"]
        assert any(f["feedback_id"] == fb_id for f in items)

    def test_upvote(self, client):
        a = register(client, "fb-voter")
        r = client.post("/api/feedback", json={
            "category": "improvement", "body": "Better documentation for agent onboarding would help a lot",
        }, headers=auth(a["token"]))
        fb_id = r.json()["feedback_id"]

        r = client.post(f"/api/feedback/{fb_id}/upvote", headers=auth(a["token"]))
        assert r.status_code == 200


class TestPublicAPI:
    def test_stats(self, client):
        r = client.get("/api/public/stats")
        assert r.status_code == 200
        s = r.json()
        assert s["currency"] == "BTC"
        assert s["unit"] == "sats"
        assert s["total_agents"] > 0

    def test_leaderboard(self, client):
        r = client.get("/api/public/leaderboard")
        assert r.status_code == 200

    def test_onboard_spec(self, client):
        r = client.get("/api/onboard/spec")
        assert r.status_code == 200
        spec = r.json()
        assert spec["platform"] == "AgentMarket"
        assert spec["currency"]["unit"] == "sats"
        assert "quick_start" in spec
        assert "endpoints" in spec
        assert "earning_opportunities" in spec

    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestAdmin:
    def test_admin_stats(self, client):
        r = client.get("/api/admin/stats", headers={"Authorization": "Bearer test-admin-token"})
        assert r.status_code == 200
        s = r.json()
        assert "platform_revenue_sats" in s
        assert "platform_fee_bps" in s
        assert s["platform_fee_bps"] == 600

    def test_admin_bad_token(self, client):
        r = client.get("/api/admin/stats", headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 403
