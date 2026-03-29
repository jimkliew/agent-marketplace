"""Authentication — HMAC-SHA256 token system."""

import hmac
import hashlib
import secrets
from fastapi import Request, HTTPException
from backend.config import SECRET_KEY, ADMIN_TOKEN
from backend.database import db_fetchone


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
        "SELECT agent_id, status FROM agents WHERE token_hash = ?",
        (hash_token(token),),
    )
    if not agent:
        raise HTTPException(401, "Invalid token")
    if agent["status"] != "active":
        raise HTTPException(403, f"Agent is {agent['status']}")
    request.state.agent_id = agent["agent_id"]
    return agent["agent_id"]


async def require_admin(request: Request) -> bool:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing Authorization header")
    if not hmac.compare_digest(auth[7:], ADMIN_TOKEN):
        raise HTTPException(403, "Invalid admin token")
    return True
