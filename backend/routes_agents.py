"""Agent registration and ANS lookup. All balances in satoshis."""

import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from backend.auth import require_agent, generate_token, hash_token
from backend.database import get_db, db_fetchone, db_fetchall
from backend.events import append_event
from backend.security import check_rate_limit, sanitize_text
from backend.config import RATE_LIMIT_REGISTER, MIN_DEPOSIT
from backend.models import AgentRegisterRequest, AgentRegisterResponse, AgentProfile

router = APIRouter()


@router.post("/register", response_model=AgentRegisterResponse)
async def register_agent(req: AgentRegisterRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    check_rate_limit(f"register:{ip}", *RATE_LIMIT_REGISTER)

    agent_id = str(uuid.uuid4())
    token = generate_token()
    token_hashed = hash_token(token)
    name = req.agent_name
    display = sanitize_text(req.display_name)
    desc = sanitize_text(req.description)

    import asyncio
    def _create():
        with get_db() as conn:
            existing = conn.execute("SELECT 1 FROM agents WHERE agent_name = ?", (name,)).fetchone()
            if existing:
                raise ValueError("duplicate")
            conn.execute(
                "INSERT INTO agents (agent_id, agent_name, display_name, description, token_hash, balance) VALUES (?,?,?,?,?,0)",
                (agent_id, name, display, desc, token_hashed),
            )
    try:
        await asyncio.to_thread(_create)
    except ValueError:
        raise HTTPException(409, f"Agent name '{name}' already taken")

    await append_event("agent.registered", agent_id, "agent", agent_id, {"agent_name": name}, ip)
    return AgentRegisterResponse(
        agent_id=agent_id, agent_name=name, token=token,
        balance=0, email=f"{name}@agentmarket.local",
    )


@router.get("/lookup/{agent_name}", response_model=AgentProfile)
async def lookup_agent(agent_name: str):
    agent = await db_fetchone(
        "SELECT agent_id, agent_name, display_name, description, status, reputation, jobs_completed, jobs_posted, created_at FROM agents WHERE agent_name = ?",
        (agent_name,),
    )
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


@router.get("/{agent_id}", response_model=AgentProfile)
async def get_agent(agent_id: str):
    agent = await db_fetchone(
        "SELECT agent_id, agent_name, display_name, description, status, reputation, jobs_completed, jobs_posted, created_at FROM agents WHERE agent_id = ?",
        (agent_id,),
    )
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


@router.get("")
async def list_agents(page: int = 1, page_size: int = 20):
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size
    agents = await db_fetchall(
        "SELECT agent_id, agent_name, display_name, description, status, reputation, jobs_completed, jobs_posted, created_at FROM agents WHERE status = 'active' ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (page_size, offset),
    )
    total = await db_fetchone("SELECT COUNT(*) as c FROM agents WHERE status = 'active'")
    return {"items": agents, "total": total["c"], "page": page, "page_size": page_size}


@router.patch("/{agent_id}")
async def update_agent(agent_id: str, request: Request, _=Depends(require_agent)):
    if request.state.agent_id != agent_id:
        raise HTTPException(403, "Can only update own profile")
    body = await request.json()
    updates, params = [], []
    if "display_name" in body:
        updates.append("display_name = ?"); params.append(sanitize_text(body["display_name"])[:100])
    if "description" in body:
        updates.append("description = ?"); params.append(sanitize_text(body["description"])[:500])
    if not updates:
        raise HTTPException(400, "Nothing to update")
    updates.append("updated_at = datetime('now')")
    params.append(agent_id)
    import asyncio
    def _update():
        with get_db() as conn:
            conn.execute(f"UPDATE agents SET {', '.join(updates)} WHERE agent_id = ?", tuple(params))
    await asyncio.to_thread(_update)
    await append_event("agent.updated", agent_id, "agent", agent_id, body)
    return {"status": "updated"}


@router.get("/{agent_id}/balance")
async def get_balance(agent_id: str, request: Request, _=Depends(require_agent)):
    if request.state.agent_id != agent_id:
        raise HTTPException(403, "Can only view own balance")
    agent = await db_fetchone("SELECT balance FROM agents WHERE agent_id = ?", (agent_id,))
    if not agent:
        raise HTTPException(404, "Agent not found")
    return {"agent_id": agent_id, "balance": agent["balance"], "unit": "sats"}
