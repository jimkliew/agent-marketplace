"""Ratings — post-job reviews between agents. Both poster and worker can rate."""

import uuid
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from backend.auth import require_agent
from backend.database import get_db, db_fetchone, db_fetchall
from backend.events import append_event
from backend.security import sanitize_text

router = APIRouter()


class RatingRequest(BaseModel):
    score: int = Field(ge=1, le=5, description="1-5 stars")
    review: str = Field(default="", max_length=1000)


@router.post("/jobs/{job_id}/rate")
async def rate_agent(job_id: str, req: RatingRequest, agent_id: str = Depends(require_agent)):
    """Rate the other party after a completed job. Poster rates worker, worker rates poster."""
    job = await db_fetchone("SELECT poster_id, assigned_to, status FROM jobs WHERE job_id = ?", (job_id,))
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "completed":
        raise HTTPException(400, "Can only rate completed jobs")
    if agent_id not in (job["poster_id"], job["assigned_to"]):
        raise HTTPException(403, "Only poster or worker can rate")

    # Determine who's being rated
    if agent_id == job["poster_id"]:
        to_agent_id = job["assigned_to"]
        role = "poster"
    else:
        to_agent_id = job["poster_id"]
        role = "worker"

    rating_id = str(uuid.uuid4())
    review = sanitize_text(req.review)

    def _rate():
        with get_db() as conn:
            # Check for existing rating
            existing = conn.execute(
                "SELECT 1 FROM ratings WHERE job_id = ? AND from_agent_id = ?",
                (job_id, agent_id),
            ).fetchone()
            if existing:
                raise ValueError("already rated")

            conn.execute(
                "INSERT INTO ratings (rating_id, job_id, from_agent_id, to_agent_id, score, review, role) VALUES (?,?,?,?,?,?,?)",
                (rating_id, job_id, agent_id, to_agent_id, req.score, review, role),
            )

            # Update reputation: weighted average of all ratings received
            avg = conn.execute(
                "SELECT AVG(score) as avg_score, COUNT(*) as count FROM ratings WHERE to_agent_id = ?",
                (to_agent_id,),
            ).fetchone()
            if avg and avg["count"] > 0:
                conn.execute(
                    "UPDATE agents SET reputation = ?, updated_at = datetime('now') WHERE agent_id = ?",
                    (round(avg["avg_score"], 2), to_agent_id),
                )

    try:
        await asyncio.to_thread(_rate)
    except ValueError:
        raise HTTPException(409, "You already rated this job")

    await append_event("rating.submitted", agent_id, "rating", rating_id, {
        "job_id": job_id, "to": to_agent_id, "score": req.score, "role": role,
    })
    return {"rating_id": rating_id, "score": req.score, "to_agent_id": to_agent_id}


@router.get("/agents/{agent_id}/ratings")
async def get_agent_ratings(agent_id: str, page: int = 1, page_size: int = 20):
    """Get all ratings received by an agent. Public."""
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size
    ratings = await db_fetchall(
        """SELECT r.*, a.agent_name as from_agent_name, j.title as job_title
           FROM ratings r
           JOIN agents a ON r.from_agent_id = a.agent_id
           JOIN jobs j ON r.job_id = j.job_id
           WHERE r.to_agent_id = ?
           ORDER BY r.created_at DESC LIMIT ? OFFSET ?""",
        (agent_id, page_size, offset),
    )
    avg = await db_fetchone(
        "SELECT AVG(score) as avg_score, COUNT(*) as count FROM ratings WHERE to_agent_id = ?",
        (agent_id,),
    )
    return {
        "ratings": ratings,
        "average_score": round(avg["avg_score"], 2) if avg and avg["avg_score"] else 0,
        "total_ratings": avg["count"] if avg else 0,
        "page": page,
    }


@router.get("/jobs/{job_id}/ratings")
async def get_job_ratings(job_id: str):
    """Get all ratings for a specific job."""
    return await db_fetchall(
        """SELECT r.*, a.agent_name as from_agent_name
           FROM ratings r JOIN agents a ON r.from_agent_id = a.agent_id
           WHERE r.job_id = ? ORDER BY r.created_at""",
        (job_id,),
    )
