"""Job marketplace — post, bid, accept, submit, approve. All prices in satoshis."""

import json
import uuid
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request
from backend.auth import require_agent
from backend.database import get_db, db_fetchone, db_fetchall
from backend.events import append_event
from backend.escrow import lock_funds, release_funds, refund_funds
from backend.security import check_rate_limit, sanitize_text
from backend.config import RATE_LIMIT_JOB_POST, RATE_LIMIT_BID, PAYMENT_UNIT
from backend.models import JobCreateRequest, JobResponse, JobSubmitRequest, BidCreateRequest

router = APIRouter()


@router.post("", response_model=JobResponse)
async def create_job(req: JobCreateRequest, request: Request, agent_id: str = Depends(require_agent)):
    check_rate_limit(f"job:{agent_id}", *RATE_LIMIT_JOB_POST)
    job_id = str(uuid.uuid4())
    goals_json = json.dumps(req.goals)
    tags_json = json.dumps(req.tags)
    title = sanitize_text(req.title)
    desc = sanitize_text(req.description)

    def _create():
        with get_db() as conn:
            # Job must exist before escrow (foreign key constraint)
            conn.execute(
                "INSERT INTO jobs (job_id, poster_id, title, description, goals, tags, price, status) VALUES (?,?,?,?,?,?,?,'open')",
                (job_id, agent_id, title, desc, goals_json, tags_json, req.price),
            )
            escrow_id = lock_funds(conn, agent_id, job_id, req.price)
            return escrow_id
    try:
        escrow_id = await asyncio.to_thread(_create)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await append_event("job.created", agent_id, "job", job_id, {"title": title, "price": req.price, "unit": PAYMENT_UNIT})
    await append_event("escrow.locked", agent_id, "escrow", escrow_id, {"amount": req.price, "unit": PAYMENT_UNIT})

    poster = await db_fetchone("SELECT agent_name FROM agents WHERE agent_id = ?", (agent_id,))
    return JobResponse(
        job_id=job_id, poster_id=agent_id, poster_name=poster["agent_name"] if poster else None,
        title=title, description=desc, goals=req.goals, tags=req.tags,
        price=req.price, status="open", assigned_to=None, result=None,
        created_at="", updated_at="",
    )


@router.get("")
async def list_jobs(status: str | None = None, tag: str | None = None, page: int = 1, page_size: int = 20):
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size
    conditions, params = [], []
    if status:
        conditions.append("j.status = ?"); params.append(status)
    if tag:
        conditions.append("j.tags LIKE ?"); params.append(f'%"{tag}"%')
    where = " AND ".join(conditions) if conditions else "1=1"
    jobs = await db_fetchall(
        f"SELECT j.*, a.agent_name as poster_name FROM jobs j JOIN agents a ON j.poster_id = a.agent_id WHERE {where} ORDER BY j.created_at DESC LIMIT ? OFFSET ?",
        tuple(params + [page_size, offset]),
    )
    for j in jobs:
        j["goals"] = json.loads(j["goals"])
        j["tags"] = json.loads(j["tags"])
    total = await db_fetchone(f"SELECT COUNT(*) as c FROM jobs j WHERE {where}", tuple(params))
    return {"items": jobs, "total": total["c"], "page": page, "page_size": page_size}


@router.get("/{job_id}")
async def get_job(job_id: str):
    job = await db_fetchone(
        "SELECT j.*, a.agent_name as poster_name FROM jobs j JOIN agents a ON j.poster_id = a.agent_id WHERE j.job_id = ?",
        (job_id,),
    )
    if not job:
        raise HTTPException(404, "Job not found")
    job["goals"] = json.loads(job["goals"])
    job["tags"] = json.loads(job["tags"])
    bids = await db_fetchall(
        "SELECT b.*, a.agent_name as bidder_name FROM bids b JOIN agents a ON b.bidder_id = a.agent_id WHERE b.job_id = ? ORDER BY b.created_at",
        (job_id,),
    )
    return {**job, "bids": bids}


@router.post("/{job_id}/bid")
async def submit_bid(job_id: str, req: BidCreateRequest, request: Request, agent_id: str = Depends(require_agent)):
    check_rate_limit(f"bid:{agent_id}", *RATE_LIMIT_BID)
    job = await db_fetchone("SELECT poster_id, status FROM jobs WHERE job_id = ?", (job_id,))
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "open":
        raise HTTPException(400, "Job is not open for bids")
    if job["poster_id"] == agent_id:
        raise HTTPException(403, "Cannot bid on your own job")

    bid_id = str(uuid.uuid4())
    msg = sanitize_text(req.message)
    def _bid():
        with get_db() as conn:
            conn.execute(
                "INSERT INTO bids (bid_id, job_id, bidder_id, amount, message) VALUES (?,?,?,?,?)",
                (bid_id, job_id, agent_id, req.amount, msg),
            )
    try:
        await asyncio.to_thread(_bid)
    except Exception:
        raise HTTPException(409, "You already bid on this job")

    await append_event("bid.submitted", agent_id, "bid", bid_id, {"job_id": job_id, "amount": req.amount, "unit": PAYMENT_UNIT})
    return {"bid_id": bid_id, "status": "pending"}


@router.post("/{job_id}/accept-bid/{bid_id}")
async def accept_bid(job_id: str, bid_id: str, request: Request, agent_id: str = Depends(require_agent)):
    job = await db_fetchone("SELECT poster_id, status FROM jobs WHERE job_id = ?", (job_id,))
    if not job:
        raise HTTPException(404, "Job not found")
    if job["poster_id"] != agent_id:
        raise HTTPException(403, "Only the poster can accept bids")
    if job["status"] != "open":
        raise HTTPException(400, "Job is not open")

    bid = await db_fetchone("SELECT bidder_id, amount FROM bids WHERE bid_id = ? AND job_id = ?", (bid_id, job_id))
    if not bid:
        raise HTTPException(404, "Bid not found")

    def _accept():
        with get_db() as conn:
            conn.execute("UPDATE bids SET status = 'accepted' WHERE bid_id = ?", (bid_id,))
            conn.execute("UPDATE bids SET status = 'rejected' WHERE job_id = ? AND bid_id != ?", (job_id, bid_id))
            conn.execute("UPDATE jobs SET status = 'assigned', assigned_to = ?, updated_at = datetime('now') WHERE job_id = ?", (bid["bidder_id"], job_id))
            conn.execute("UPDATE escrow SET payee_id = ? WHERE job_id = ?", (bid["bidder_id"], job_id))
    await asyncio.to_thread(_accept)
    await append_event("bid.accepted", agent_id, "bid", bid_id, {"bidder_id": bid["bidder_id"]})
    await append_event("job.assigned", agent_id, "job", job_id, {"assigned_to": bid["bidder_id"]})
    return {"status": "assigned", "assigned_to": bid["bidder_id"]}


@router.post("/{job_id}/submit")
async def submit_work(job_id: str, req: JobSubmitRequest, request: Request, agent_id: str = Depends(require_agent)):
    job = await db_fetchone("SELECT assigned_to, status FROM jobs WHERE job_id = ?", (job_id,))
    if not job:
        raise HTTPException(404, "Job not found")
    if job["assigned_to"] != agent_id:
        raise HTTPException(403, "Only the assigned worker can submit")
    if job["status"] not in ("assigned", "in_progress"):
        raise HTTPException(400, f"Cannot submit work for job in status: {job['status']}")

    result = sanitize_text(req.result)
    def _submit():
        with get_db() as conn:
            conn.execute("UPDATE jobs SET status = 'review', result = ?, updated_at = datetime('now') WHERE job_id = ?", (result, job_id))
    await asyncio.to_thread(_submit)
    await append_event("job.submitted", agent_id, "job", job_id, {"result_preview": result[:200]})
    return {"status": "review"}


@router.post("/{job_id}/approve")
async def approve_work(job_id: str, request: Request, agent_id: str = Depends(require_agent)):
    job = await db_fetchone("SELECT poster_id, status, assigned_to FROM jobs WHERE job_id = ?", (job_id,))
    if not job:
        raise HTTPException(404, "Job not found")
    if job["poster_id"] != agent_id:
        raise HTTPException(403, "Only the poster can approve work")
    if job["status"] != "review":
        raise HTTPException(400, "Job is not in review status")

    escrow = await db_fetchone("SELECT escrow_id FROM escrow WHERE job_id = ? AND status = 'held'", (job_id,))
    if not escrow:
        raise HTTPException(400, "Escrow not found")

    def _approve():
        with get_db() as conn:
            release_funds(conn, escrow["escrow_id"])
            conn.execute("UPDATE jobs SET status = 'completed', updated_at = datetime('now') WHERE job_id = ?", (job_id,))
            conn.execute("UPDATE agents SET jobs_completed = jobs_completed + 1, reputation = reputation + 1.0 WHERE agent_id = ?", (job["assigned_to"],))
            conn.execute("UPDATE agents SET jobs_posted = jobs_posted + 1 WHERE agent_id = ?", (agent_id,))
    await asyncio.to_thread(_approve)
    await append_event("job.completed", agent_id, "job", job_id, {"worker": job["assigned_to"]})
    await append_event("escrow.released", "system", "escrow", escrow["escrow_id"], {"payee": job["assigned_to"]})
    return {"status": "completed"}


@router.post("/{job_id}/dispute")
async def dispute_job(job_id: str, request: Request, agent_id: str = Depends(require_agent)):
    job = await db_fetchone("SELECT poster_id, assigned_to, status FROM jobs WHERE job_id = ?", (job_id,))
    if not job:
        raise HTTPException(404, "Job not found")
    if agent_id not in (job["poster_id"], job["assigned_to"]):
        raise HTTPException(403, "Only poster or assigned worker can dispute")
    if job["status"] not in ("assigned", "in_progress", "review"):
        raise HTTPException(400, "Cannot dispute job in current status")

    def _dispute():
        with get_db() as conn:
            conn.execute("UPDATE jobs SET status = 'disputed', updated_at = datetime('now') WHERE job_id = ?", (job_id,))
            conn.execute("UPDATE escrow SET status = 'disputed' WHERE job_id = ?", (job_id,))
    await asyncio.to_thread(_dispute)
    await append_event("job.disputed", agent_id, "job", job_id, {"disputed_by": agent_id})
    return {"status": "disputed"}


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request, agent_id: str = Depends(require_agent)):
    job = await db_fetchone("SELECT poster_id, status FROM jobs WHERE job_id = ?", (job_id,))
    if not job:
        raise HTTPException(404, "Job not found")
    if job["poster_id"] != agent_id:
        raise HTTPException(403, "Only the poster can cancel")
    if job["status"] != "open":
        raise HTTPException(400, "Can only cancel open jobs")

    escrow = await db_fetchone("SELECT escrow_id FROM escrow WHERE job_id = ?", (job_id,))
    def _cancel():
        with get_db() as conn:
            if escrow:
                refund_funds(conn, escrow["escrow_id"])
            conn.execute("UPDATE jobs SET status = 'cancelled', updated_at = datetime('now') WHERE job_id = ?", (job_id,))
    await asyncio.to_thread(_cancel)
    await append_event("job.cancelled", agent_id, "job", job_id, {})
    return {"status": "cancelled"}
