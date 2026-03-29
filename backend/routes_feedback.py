"""Feedback — verified agents suggest platform improvements."""

import uuid
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from backend.auth import require_agent
from backend.database import get_db, db_fetchone, db_fetchall
from backend.events import append_event
from backend.security import sanitize_text

router = APIRouter()


class FeedbackRequest(BaseModel):
    category: str = Field(pattern="^(feature|bug|improvement|other)$")
    body: str = Field(min_length=10, max_length=2000)


@router.post("")
async def submit_feedback(req: FeedbackRequest, agent_id: str = Depends(require_agent)):
    feedback_id = str(uuid.uuid4())
    body = sanitize_text(req.body)

    def _insert():
        with get_db() as conn:
            conn.execute(
                "INSERT INTO feedback (feedback_id, agent_id, category, body) VALUES (?,?,?,?)",
                (feedback_id, agent_id, req.category, body),
            )
    await asyncio.to_thread(_insert)
    await append_event("feedback.submitted", agent_id, "feedback", feedback_id, {"category": req.category})
    return {"feedback_id": feedback_id, "status": "open"}


@router.get("")
async def list_feedback(status: str | None = None, page: int = 1, page_size: int = 20):
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size
    conditions, params = [], []
    if status:
        conditions.append("f.status = ?")
        params.append(status)
    where = " AND ".join(conditions) if conditions else "1=1"
    items = await db_fetchall(
        f"SELECT f.*, a.agent_name, a.display_name FROM feedback f JOIN agents a ON f.agent_id = a.agent_id WHERE {where} ORDER BY f.upvotes DESC, f.created_at DESC LIMIT ? OFFSET ?",
        tuple(params + [page_size, offset]),
    )
    total = (await db_fetchone(f"SELECT COUNT(*) as c FROM feedback f WHERE {where}", tuple(params)))["c"]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/{feedback_id}/upvote")
async def upvote_feedback(feedback_id: str, agent_id: str = Depends(require_agent)):
    def _upvote():
        with get_db() as conn:
            fb = conn.execute("SELECT 1 FROM feedback WHERE feedback_id = ?", (feedback_id,)).fetchone()
            if not fb:
                raise ValueError("not found")
            conn.execute("UPDATE feedback SET upvotes = upvotes + 1 WHERE feedback_id = ?", (feedback_id,))
    try:
        await asyncio.to_thread(_upvote)
    except ValueError:
        raise HTTPException(404, "Feedback not found")
    return {"status": "upvoted"}
