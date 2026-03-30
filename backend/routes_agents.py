"""Agent registration and ANS lookup. All balances in satoshis."""

import os
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


WELCOME_BONUS = int(os.getenv("WELCOME_BONUS", "1000"))  # 1,000 sats free on signup


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
    referrer = sanitize_text(req.referrer) if hasattr(req, 'referrer') and req.referrer else None

    import asyncio
    def _create():
        with get_db() as conn:
            existing = conn.execute("SELECT 1 FROM agents WHERE agent_name = ?", (name,)).fetchone()
            if existing:
                raise ValueError("duplicate")
            # Register with welcome bonus
            conn.execute(
                "INSERT INTO agents (agent_id, agent_name, display_name, description, token_hash, balance) VALUES (?,?,?,?,?,?)",
                (agent_id, name, display, desc, token_hashed, WELCOME_BONUS),
            )
            # Ledger entry for welcome bonus
            if WELCOME_BONUS > 0:
                import uuid as _uuid
                tx_id = str(_uuid.uuid4())
                conn.execute(
                    "INSERT INTO ledger (tx_id, from_agent_id, to_agent_id, amount, currency, unit, tx_type, description) VALUES (?,NULL,?,?,?,?,'deposit',?)",
                    (tx_id, agent_id, WELCOME_BONUS, 'BTC', 'sats', f"Welcome bonus: {WELCOME_BONUS} sats"),
                )
            # Referral tracking
            if referrer:
                ref_agent = conn.execute("SELECT agent_id FROM agents WHERE agent_name = ?", (referrer,)).fetchone()
                if ref_agent:
                    conn.execute(
                        "INSERT INTO events (event_id, event_type, actor_id, entity_type, entity_id, data) VALUES (?,?,?,?,?,?)",
                        (str(_uuid.uuid4()), "referral.registered", agent_id, "agent", ref_agent["agent_id"],
                         json.dumps({"referred": name, "referrer": referrer})),
                    )
    try:
        await asyncio.to_thread(_create)
    except ValueError:
        raise HTTPException(409, f"Agent name '{name}' already taken")

    await append_event("agent.registered", agent_id, "agent", agent_id,
        {"agent_name": name, "welcome_bonus": WELCOME_BONUS, "referrer": referrer}, ip)
    return AgentRegisterResponse(
        agent_id=agent_id, agent_name=name, token=token,
        balance=WELCOME_BONUS, email=f"{name}@agentmarket.local",
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
