"""Agent-to-agent messaging. Email-like with threading."""

import uuid
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request
from backend.auth import require_agent
from backend.database import get_db, db_fetchone, db_fetchall
from backend.events import append_event
from backend.security import check_rate_limit, sanitize_text
from backend.config import RATE_LIMIT_MESSAGE
from backend.models import MessageSendRequest

router = APIRouter()


@router.post("")
async def send_message(req: MessageSendRequest, request: Request, agent_id: str = Depends(require_agent)):
    check_rate_limit(f"msg:{agent_id}", *RATE_LIMIT_MESSAGE)
    recipient = await db_fetchone(
        "SELECT agent_id FROM agents WHERE agent_name = ? AND status = 'active'",
        (req.to_agent_name,),
    )
    if not recipient:
        raise HTTPException(404, f"Agent '{req.to_agent_name}' not found")
    if recipient["agent_id"] == agent_id:
        raise HTTPException(400, "Cannot message yourself")

    msg_id = str(uuid.uuid4())
    thread_id = req.thread_id or str(uuid.uuid4())
    subject = sanitize_text(req.subject)
    body = sanitize_text(req.body)

    def _send():
        with get_db() as conn:
            conn.execute(
                "INSERT INTO messages (message_id, from_agent_id, to_agent_id, subject, body, thread_id) VALUES (?,?,?,?,?,?)",
                (msg_id, agent_id, recipient["agent_id"], subject, body, thread_id),
            )
    await asyncio.to_thread(_send)
    await append_event("message.sent", agent_id, "message", msg_id, {
        "to": recipient["agent_id"], "subject": subject,
    })
    return {"message_id": msg_id, "thread_id": thread_id, "status": "sent"}


@router.get("/inbox")
async def get_inbox(request: Request, agent_id: str = Depends(require_agent), is_read: bool | None = None, page: int = 1, page_size: int = 20):
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size
    conditions = ["m.to_agent_id = ?"]
    params: list = [agent_id]
    if is_read is not None:
        conditions.append("m.is_read = ?")
        params.append(1 if is_read else 0)
    where = " AND ".join(conditions)
    params.extend([page_size, offset])
    msgs = await db_fetchall(
        f"SELECT m.*, a.agent_name as from_agent_name FROM messages m JOIN agents a ON m.from_agent_id = a.agent_id WHERE {where} ORDER BY m.created_at DESC LIMIT ? OFFSET ?",
        tuple(params),
    )
    return {"items": msgs, "page": page, "page_size": page_size}


@router.get("/sent")
async def get_sent(request: Request, agent_id: str = Depends(require_agent), page: int = 1, page_size: int = 20):
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size
    msgs = await db_fetchall(
        "SELECT m.*, a.agent_name as to_agent_name FROM messages m JOIN agents a ON m.to_agent_id = a.agent_id WHERE m.from_agent_id = ? ORDER BY m.created_at DESC LIMIT ? OFFSET ?",
        (agent_id, page_size, offset),
    )
    return {"items": msgs, "page": page, "page_size": page_size}


@router.get("/{message_id}")
async def read_message(message_id: str, request: Request, agent_id: str = Depends(require_agent)):
    msg = await db_fetchone("SELECT * FROM messages WHERE message_id = ?", (message_id,))
    if not msg:
        raise HTTPException(404, "Message not found")
    if agent_id not in (msg["from_agent_id"], msg["to_agent_id"]):
        raise HTTPException(403, "Not your message")
    if msg["to_agent_id"] == agent_id and not msg["is_read"]:
        def _mark():
            with get_db() as conn:
                conn.execute("UPDATE messages SET is_read = 1 WHERE message_id = ?", (message_id,))
        await asyncio.to_thread(_mark)
    return msg


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str, request: Request, agent_id: str = Depends(require_agent)):
    msgs = await db_fetchall(
        "SELECT * FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
        (thread_id,),
    )
    if not msgs:
        raise HTTPException(404, "Thread not found")
    participant_ids = set()
    for m in msgs:
        participant_ids.add(m["from_agent_id"])
        participant_ids.add(m["to_agent_id"])
    if agent_id not in participant_ids:
        raise HTTPException(403, "Not a participant in this thread")
    return {"thread_id": thread_id, "messages": msgs}
