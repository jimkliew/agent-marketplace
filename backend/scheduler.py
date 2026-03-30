"""Background scheduler — enforces job deadlines and auto-refunds expired escrow.

Runs periodically to:
  1. Find assigned/in_progress jobs past their deadline
  2. Auto-refund escrowed sats to poster
  3. Log the timeout event

Integrated into FastAPI lifespan via asyncio task.
"""

import asyncio
from backend.database import get_db, db_fetchall
from backend.escrow import refund_funds
from backend.events import append_event

CHECK_INTERVAL_SECONDS = 60  # Check every minute


async def enforce_deadlines():
    """Find expired jobs and auto-refund."""
    def _find_expired():
        with get_db() as conn:
            return [dict(r) for r in conn.execute(
                """SELECT j.job_id, j.title, j.poster_id, e.escrow_id
                   FROM jobs j
                   JOIN escrow e ON j.job_id = e.job_id
                   WHERE j.deadline_at IS NOT NULL
                     AND j.deadline_at < datetime('now')
                     AND j.status IN ('open', 'assigned', 'in_progress')
                     AND e.status = 'held'"""
            ).fetchall()]

    expired = await asyncio.to_thread(_find_expired)

    for job in expired:
        try:
            def _refund(j=job):
                with get_db() as conn:
                    refund_funds(conn, j["escrow_id"])
                    conn.execute(
                        "UPDATE jobs SET status = 'cancelled', updated_at = datetime('now') WHERE job_id = ?",
                        (j["job_id"],),
                    )
            await asyncio.to_thread(_refund)
            await append_event("job.expired", "system", "job", job["job_id"], {
                "reason": "deadline_passed", "refunded_to": job["poster_id"],
            })
            print(f"[Scheduler] Auto-refunded expired job: {job['title'][:40]}")
        except Exception as e:
            print(f"[Scheduler] Failed to refund {job['job_id'][:8]}: {e}")

    return len(expired)


async def deadline_loop():
    """Background loop that checks for expired jobs."""
    while True:
        try:
            count = await enforce_deadlines()
            if count > 0:
                print(f"[Scheduler] Processed {count} expired jobs")
        except Exception as e:
            print(f"[Scheduler] Error: {e}")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
