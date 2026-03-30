"""Authentication — HMAC-SHA256 tokens with expiry and rotation."""

import hmac
import hashlib
import secrets
import asyncio
from fastapi import APIRouter, Request, HTTPException, Depends
from backend.config import SECRET_KEY, ADMIN_TOKEN
from backend.database import db_fetchone, get_db

router = APIRouter()

TOKEN_EXPIRY_DAYS = 30


def generate_token() -> str:
    return secrets.token_hex(32)


def hash_token(token: str) -> str:
    return hmac.new(SECRET_KEY.encode(), token.encode(), hashlib.sha256).hexdigest()


async def require_agent(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")
    token = auth[7:]
    agent = await db_fetchone(
        "SELECT agent_id, status, token_expires_at FROM agents WHERE token_hash = ?",
        (hash_token(token),),
    )
    if not agent:
        raise HTTPException(401, "Invalid token")
    if agent["status"] != "active":
        raise HTTPException(403, f"Agent is {agent['status']}")
    # Check expiry
    if agent.get("token_expires_at"):
        expires = agent["token_expires_at"]
        def _check():
            import sqlite3
            conn = sqlite3.connect(":memory:")
            now = conn.execute("SELECT datetime('now')").fetchone()[0]
            conn.close()
            return now > expires
        if await asyncio.to_thread(_check):
            raise HTTPException(401, "Token expired. Call POST /api/agents/rotate-token with your current token to get a new one.")
    request.state.agent_id = agent["agent_id"]
    return agent["agent_id"]


async def require_admin(request: Request) -> bool:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing Authorization header")
    if not hmac.compare_digest(auth[7:], ADMIN_TOKEN):
        raise HTTPException(403, "Invalid admin token")
    return True


@router.post("/rotate-token")
async def rotate_token(request: Request):
    """Rotate agent token. Requires current (possibly expired) token. Returns new token valid for 30 days."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing Authorization header")
    old_token = auth[7:]
    old_hash = hash_token(old_token)

    # Allow expired tokens for rotation (so agents can recover)
    agent = await db_fetchone(
        "SELECT agent_id, agent_name FROM agents WHERE token_hash = ? AND status = 'active'",
        (old_hash,),
    )
    if not agent:
        raise HTTPException(401, "Invalid token or agent suspended")

    new_token = generate_token()
    new_hash = hash_token(new_token)

    def _rotate():
        with get_db() as conn:
            conn.execute(
                "UPDATE agents SET token_hash = ?, token_expires_at = datetime('now', '+30 days'), updated_at = datetime('now') WHERE agent_id = ?",
                (new_hash, agent["agent_id"]),
            )
    await asyncio.to_thread(_rotate)

    from backend.events import append_event
    await append_event("agent.token_rotated", agent["agent_id"], "agent", agent["agent_id"], {})

    return {
        "agent_id": agent["agent_id"],
        "agent_name": agent["agent_name"],
        "token": new_token,
        "expires_in_days": TOKEN_EXPIRY_DAYS,
        "note": "Save this token. The old token is now invalid.",
    }
