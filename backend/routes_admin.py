"""Admin dashboard API. All endpoints require admin token."""

import asyncio
from fastapi import APIRouter, Depends, HTTPException
from backend.auth import require_admin
from backend.database import get_db, db_fetchone, db_fetchall
from backend.events import query_events, append_event
from backend.escrow import release_funds, refund_funds

router = APIRouter()


@router.get("/stats")
async def admin_stats(_=Depends(require_admin)):
    stats = {}
    stats["total_agents"] = (await db_fetchone("SELECT COUNT(*) as c FROM agents"))["c"]
    stats["active_agents"] = (await db_fetchone("SELECT COUNT(*) as c FROM agents WHERE status='active'"))["c"]
    stats["suspended_agents"] = (await db_fetchone("SELECT COUNT(*) as c FROM agents WHERE status='suspended'"))["c"]
    stats["total_jobs"] = (await db_fetchone("SELECT COUNT(*) as c FROM jobs"))["c"]
    stats["open_jobs"] = (await db_fetchone("SELECT COUNT(*) as c FROM jobs WHERE status='open'"))["c"]
    stats["completed_jobs"] = (await db_fetchone("SELECT COUNT(*) as c FROM jobs WHERE status='completed'"))["c"]
    stats["disputed_jobs"] = (await db_fetchone("SELECT COUNT(*) as c FROM jobs WHERE status='disputed'"))["c"]
    held = await db_fetchone("SELECT COALESCE(SUM(amount),0) as s FROM escrow WHERE status='held'")
    stats["escrow_held_sats"] = held["s"]
    released = await db_fetchone("SELECT COALESCE(SUM(amount),0) as s FROM escrow WHERE status='released'")
    stats["total_released_sats"] = released["s"]
    stats["total_messages"] = (await db_fetchone("SELECT COUNT(*) as c FROM messages"))["c"]
    stats["total_events"] = (await db_fetchone("SELECT COUNT(*) as c FROM events"))["c"]
    total_balance = await db_fetchone("SELECT COALESCE(SUM(balance),0) as s FROM agents")
    stats["total_balance_sats"] = total_balance["s"]
    # Platform revenue
    fees = await db_fetchone("SELECT COALESCE(SUM(amount),0) as s, COUNT(*) as c FROM ledger WHERE tx_type='platform_fee'")
    stats["platform_revenue_sats"] = fees["s"]
    stats["platform_fee_count"] = fees["c"]
    from backend.config import PLATFORM_FEE_BPS
    stats["platform_fee_bps"] = PLATFORM_FEE_BPS
    return stats


@router.get("/metrics")
async def admin_metrics(days: int = 1, _=Depends(require_admin)):
    """Daily metrics: signups, transactions, revenue. The numbers that matter."""
    m = {}
    # Agent signups today
    signups = await db_fetchone(
        "SELECT COUNT(*) as c FROM agents WHERE created_at >= datetime('now', ?)",
        (f"-{days} days",),
    )
    m["signups"] = signups["c"]

    # Jobs completed today
    completed = await db_fetchone(
        "SELECT COUNT(*) as c FROM jobs WHERE status='completed' AND updated_at >= datetime('now', ?)",
        (f"-{days} days",),
    )
    m["jobs_completed"] = completed["c"]

    # Jobs posted today
    posted = await db_fetchone(
        "SELECT COUNT(*) as c FROM jobs WHERE created_at >= datetime('now', ?)",
        (f"-{days} days",),
    )
    m["jobs_posted"] = posted["c"]

    # Bids today
    bids = await db_fetchone(
        "SELECT COUNT(*) as c FROM bids WHERE created_at >= datetime('now', ?)",
        (f"-{days} days",),
    )
    m["bids_submitted"] = bids["c"]

    # Revenue today (platform fees)
    rev = await db_fetchone(
        "SELECT COALESCE(SUM(amount),0) as s, COUNT(*) as c FROM ledger WHERE tx_type='platform_fee' AND created_at >= datetime('now', ?)",
        (f"-{days} days",),
    )
    m["revenue_sats"] = rev["s"]
    m["fee_transactions"] = rev["c"]

    # Transaction volume today
    vol = await db_fetchone(
        "SELECT COALESCE(SUM(amount),0) as s FROM ledger WHERE tx_type='escrow_release' AND created_at >= datetime('now', ?)",
        (f"-{days} days",),
    )
    m["volume_sats"] = vol["s"]

    # Deposits today
    deps = await db_fetchone(
        "SELECT COALESCE(SUM(amount),0) as s, COUNT(*) as c FROM ledger WHERE tx_type='deposit' AND created_at >= datetime('now', ?)",
        (f"-{days} days",),
    )
    m["deposits_sats"] = deps["s"]
    m["deposit_count"] = deps["c"]

    # Withdrawals today
    withdrawals = await db_fetchone(
        "SELECT COALESCE(SUM(amount),0) as s, COUNT(*) as c FROM ledger WHERE tx_type='withdrawal' AND created_at >= datetime('now', ?)",
        (f"-{days} days",),
    )
    m["withdrawals_sats"] = withdrawals["s"]
    m["withdrawal_count"] = withdrawals["c"]

    # Messages today
    msgs = await db_fetchone(
        "SELECT COUNT(*) as c FROM messages WHERE created_at >= datetime('now', ?)",
        (f"-{days} days",),
    )
    m["messages_sent"] = msgs["c"]

    m["period_days"] = days
    m["target_revenue_sats"] = 1000
    m["target_pct"] = round((m["revenue_sats"] / 1000) * 100, 1) if m["revenue_sats"] > 0 else 0

    return m


@router.get("/events")
async def admin_events(event_type: str | None = None, entity_type: str | None = None, limit: int = 100, offset: int = 0, _=Depends(require_admin)):
    return await query_events(event_type=event_type, entity_type=entity_type, limit=min(limit, 500), offset=offset)


@router.get("/disputes")
async def admin_disputes(_=Depends(require_admin)):
    disputes = await db_fetchall(
        """SELECT j.*, e.escrow_id, e.amount, e.payer_id, e.payee_id, e.status as escrow_status,
                  a1.agent_name as poster_name, a2.agent_name as worker_name
           FROM jobs j
           JOIN escrow e ON j.job_id = e.job_id
           JOIN agents a1 ON j.poster_id = a1.agent_id
           LEFT JOIN agents a2 ON j.assigned_to = a2.agent_id
           WHERE j.status = 'disputed'
           ORDER BY j.updated_at DESC"""
    )
    return disputes


@router.post("/disputes/{job_id}/resolve")
async def resolve_dispute(job_id: str, resolution: dict, _=Depends(require_admin)):
    action = resolution.get("resolution")
    if action not in ("release", "refund"):
        raise HTTPException(400, "resolution must be 'release' or 'refund'")

    escrow = await db_fetchone("SELECT escrow_id, status FROM escrow WHERE job_id = ?", (job_id,))
    if not escrow or escrow["status"] != "disputed":
        raise HTTPException(400, "No disputed escrow for this job")

    def _resolve():
        with get_db() as conn:
            if action == "release":
                release_funds(conn, escrow["escrow_id"])
                conn.execute("UPDATE jobs SET status='completed', updated_at=datetime('now') WHERE job_id=?", (job_id,))
            else:
                refund_funds(conn, escrow["escrow_id"])
                conn.execute("UPDATE jobs SET status='cancelled', updated_at=datetime('now') WHERE job_id=?", (job_id,))
    await asyncio.to_thread(_resolve)
    await append_event(f"dispute.resolved.{action}", "admin", "job", job_id, {"resolution": action})
    return {"status": "resolved", "resolution": action}


@router.get("/agents")
async def admin_agents(_=Depends(require_admin)):
    return await db_fetchall(
        "SELECT agent_id, agent_name, display_name, balance, status, reputation, jobs_completed, jobs_posted, created_at FROM agents ORDER BY created_at DESC"
    )


@router.post("/agents/{agent_id}/credit")
async def credit_agent(agent_id: str, body: dict, _=Depends(require_admin)):
    """Admin: credit sats to an agent's balance. For seeding marketplace liquidity."""
    amount = int(body.get("amount", 0))
    if amount < 1 or amount > 100000:
        raise HTTPException(400, "Amount must be 1-100,000 sats")
    import uuid
    tx_id = str(uuid.uuid4())
    def _credit():
        with get_db() as conn:
            agent = conn.execute("SELECT agent_name FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
            if not agent:
                raise ValueError("not found")
            conn.execute("UPDATE agents SET balance = balance + ?, updated_at = datetime('now') WHERE agent_id = ?", (amount, agent_id))
            conn.execute(
                "INSERT INTO ledger (tx_id, from_agent_id, to_agent_id, amount, currency, unit, tx_type, description) VALUES (?,NULL,?,?,?,?,'deposit',?)",
                (tx_id, agent_id, amount, 'BTC', 'sats', f"Admin credit: {amount} sats"),
            )
    try:
        await asyncio.to_thread(_credit)
    except ValueError:
        raise HTTPException(404, "Agent not found")
    await append_event("admin.credit", "admin", "agent", agent_id, {"amount": amount})
    agent = await db_fetchone("SELECT balance, agent_name FROM agents WHERE agent_id = ?", (agent_id,))
    return {"agent_id": agent_id, "agent_name": agent["agent_name"], "credited": amount, "new_balance": agent["balance"]}


@router.post("/agents/{agent_id}/suspend")
async def suspend_agent(agent_id: str, _=Depends(require_admin)):
    agent = await db_fetchone("SELECT status FROM agents WHERE agent_id = ?", (agent_id,))
    if not agent:
        raise HTTPException(404, "Agent not found")

    def _suspend():
        with get_db() as conn:
            conn.execute("UPDATE agents SET status='suspended', updated_at=datetime('now') WHERE agent_id=?", (agent_id,))
    await asyncio.to_thread(_suspend)
    await append_event("agent.suspended", "admin", "agent", agent_id, {})
    return {"status": "suspended"}
