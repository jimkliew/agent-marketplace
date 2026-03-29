"""Public transparency dashboard API. No auth required."""

import json
from fastapi import APIRouter
from backend.database import db_fetchone, db_fetchall
from backend.events import query_events
from backend.config import PAYMENT_CURRENCY, PAYMENT_UNIT

router = APIRouter()


@router.get("/stats")
async def platform_stats():
    total_agents = (await db_fetchone("SELECT COUNT(*) as c FROM agents WHERE status='active'"))["c"]
    total_jobs = (await db_fetchone("SELECT COUNT(*) as c FROM jobs"))["c"]
    open_jobs = (await db_fetchone("SELECT COUNT(*) as c FROM jobs WHERE status='open'"))["c"]
    completed = (await db_fetchone("SELECT COUNT(*) as c FROM jobs WHERE status='completed'"))["c"]
    held = (await db_fetchone("SELECT COALESCE(SUM(amount),0) as s FROM escrow WHERE status='held'"))["s"]
    volume = (await db_fetchone("SELECT COALESCE(SUM(amount),0) as s FROM escrow WHERE status='released'"))["s"]
    msgs = (await db_fetchone("SELECT COUNT(*) as c FROM messages"))["c"]
    events = (await db_fetchone("SELECT COUNT(*) as c FROM events"))["c"]
    return {
        "total_agents": total_agents, "total_jobs": total_jobs,
        "open_jobs": open_jobs, "completed_jobs": completed,
        "escrow_held": held, "total_volume": volume,
        "total_messages": msgs, "total_events": events,
        "currency": PAYMENT_CURRENCY, "unit": PAYMENT_UNIT,
    }


@router.get("/activity")
async def recent_activity(limit: int = 50):
    events = await query_events(limit=min(limit, 100))
    return events


@router.get("/leaderboard")
async def agent_leaderboard():
    return await db_fetchall(
        "SELECT agent_id, agent_name, display_name, reputation, jobs_completed, jobs_posted FROM agents WHERE status='active' ORDER BY reputation DESC, jobs_completed DESC LIMIT 50"
    )


@router.get("/jobs")
async def public_jobs(status: str | None = None, page: int = 1, page_size: int = 20):
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size
    conditions, params = [], []
    if status:
        conditions.append("j.status = ?"); params.append(status)
    where = " AND ".join(conditions) if conditions else "1=1"
    jobs = await db_fetchall(
        f"SELECT j.job_id, j.title, j.description, j.goals, j.tags, j.price, j.status, j.created_at, a.agent_name as poster_name FROM jobs j JOIN agents a ON j.poster_id = a.agent_id WHERE {where} ORDER BY j.created_at DESC LIMIT ? OFFSET ?",
        tuple(params + [page_size, offset]),
    )
    for j in jobs:
        j["goals"] = json.loads(j["goals"])
        j["tags"] = json.loads(j["tags"])
    total = (await db_fetchone(f"SELECT COUNT(*) as c FROM jobs j WHERE {where}", tuple(params)))["c"]
    return {"items": jobs, "total": total, "page": page, "page_size": page_size}


@router.get("/categories")
async def job_categories():
    jobs = await db_fetchall("SELECT tags FROM jobs WHERE status != 'cancelled'")
    tag_counts: dict[str, int] = {}
    for j in jobs:
        for tag in json.loads(j["tags"]):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    return sorted([{"tag": t, "count": c} for t, c in tag_counts.items()], key=lambda x: -x["count"])
