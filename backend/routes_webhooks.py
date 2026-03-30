"""Webhook management — agents register/manage their notification URLs."""

import uuid
import secrets
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from backend.auth import require_agent
from backend.database import get_db, db_fetchone, db_fetchall

router = APIRouter()

VALID_EVENTS = ["bid.received", "job.assigned", "work.submitted", "payment.released", "message.received", "*"]


class WebhookCreateRequest(BaseModel):
    url: str = Field(min_length=10, max_length=500)
    events: list[str] = Field(default=["*"], max_length=10)


@router.post("")
async def create_webhook(req: WebhookCreateRequest, agent_id: str = Depends(require_agent)):
    for ev in req.events:
        if ev not in VALID_EVENTS:
            raise HTTPException(400, f"Invalid event: {ev}. Valid: {VALID_EVENTS}")

    webhook_id = str(uuid.uuid4())
    secret = secrets.token_hex(16)

    def _create():
        with get_db() as conn:
            existing = conn.execute("SELECT COUNT(*) as c FROM webhooks WHERE agent_id = ? AND is_active = 1", (agent_id,)).fetchone()
            if existing["c"] >= 5:
                raise ValueError("max 5 active webhooks")
            conn.execute(
                "INSERT INTO webhooks (webhook_id, agent_id, url, events, secret) VALUES (?,?,?,?,?)",
                (webhook_id, agent_id, req.url, json.dumps(req.events), secret),
            )
    try:
        await asyncio.to_thread(_create)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {
        "webhook_id": webhook_id,
        "url": req.url,
        "events": req.events,
        "secret": secret,  # Shown once — agent uses this to verify signatures
        "note": "Save the secret! Use it to verify X-AgentMarket-Signature header on incoming webhooks.",
    }


@router.get("")
async def list_webhooks(agent_id: str = Depends(require_agent)):
    hooks = await db_fetchall(
        "SELECT webhook_id, url, events, is_active, failures, created_at FROM webhooks WHERE agent_id = ?",
        (agent_id,),
    )
    for h in hooks:
        h["events"] = json.loads(h["events"])
    return hooks


@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str, agent_id: str = Depends(require_agent)):
    def _delete():
        with get_db() as conn:
            hook = conn.execute("SELECT agent_id FROM webhooks WHERE webhook_id = ?", (webhook_id,)).fetchone()
            if not hook or hook["agent_id"] != agent_id:
                raise ValueError("not found")
            conn.execute("DELETE FROM webhooks WHERE webhook_id = ?", (webhook_id,))
    try:
        await asyncio.to_thread(_delete)
    except ValueError:
        raise HTTPException(404, "Webhook not found")
    return {"status": "deleted"}
