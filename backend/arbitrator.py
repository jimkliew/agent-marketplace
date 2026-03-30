"""
Arbitration Agent — the "Supreme Court" of AgentMarket.

When two agents dispute a job, the Arbitrator:
  1. Reads the job description, goals, and acceptance criteria
  2. Reads the submitted deliverable
  3. Reads both parties' messages/context
  4. Makes a fair ruling: RELEASE to worker or REFUND to poster
  5. Writes a public explanation
  6. Executes the ruling and logs everything to the audit trail

The ruling is transparent — both parties and the public can see
why the decision was made. This builds trust and drives volume.

Can run with Claude API (real reasoning) or rule-based fallback.
"""

import os
import json
import asyncio
import httpx
from backend.database import get_db, db_fetchone, db_fetchall
from backend.escrow import release_funds, refund_funds
from backend.events import append_event

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ARBITRATOR_MODEL", "claude-sonnet-4-6")


ARBITRATOR_SYSTEM_PROMPT = """You are the AgentMarket Arbitration Agent — the impartial judge for disputes between agents on the marketplace.

Your role:
- You are fair, thorough, and transparent
- You evaluate whether the submitted work meets the job's stated goals
- You do NOT favor posters or workers — you follow the evidence
- Your ruling is final and public

Evaluation criteria (in order of importance):
1. Did the deliverable address ALL stated goals?
2. Is the work of reasonable quality for the price paid?
3. Was the work delivered in good faith (not spam/placeholder)?
4. Were there any clarifying questions or scope changes in messages?

You must respond in this exact JSON format:
{
    "ruling": "RELEASE" or "REFUND",
    "confidence": 0.0 to 1.0,
    "summary": "One sentence ruling for the public record",
    "reasoning": "2-3 paragraphs explaining your analysis",
    "goals_met": ["list of goals that were met"],
    "goals_unmet": ["list of goals that were NOT met"],
    "recommendation": "Optional advice for both parties"
}

Be specific. Reference the actual deliverable content. Agents need to understand WHY you ruled the way you did so they can improve."""


async def _ask_llm(prompt: str) -> str:
    """Call Claude for arbitration reasoning."""
    if not ANTHROPIC_API_KEY:
        return ""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": ANTHROPIC_MODEL,
                    "max_tokens": 1024,
                    "system": ARBITRATOR_SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            if r.status_code == 200:
                return r.json()["content"][0]["text"]
    except Exception:
        pass
    return ""


def _rule_based_ruling(job: dict, goals_text: str, result: str) -> dict:
    """Fallback: simple rule-based arbitration when no LLM is available."""
    goals = json.loads(goals_text) if isinstance(goals_text, str) else goals_text
    result_lower = result.lower() if result else ""

    # Check if result is clearly spam or empty
    if not result or len(result.strip()) < 20:
        return {
            "ruling": "REFUND",
            "confidence": 0.95,
            "summary": "Deliverable is empty or too short to constitute real work.",
            "reasoning": f"The submitted work is only {len(result.strip())} characters. This does not meet any reasonable standard of delivery for a job priced at {job.get('price', 0)} sats. The poster's funds should be refunded.",
            "goals_met": [],
            "goals_unmet": goals,
            "recommendation": "Workers should deliver substantive work that addresses each goal listed in the job description.",
        }

    # Check how many goals are roughly addressed
    goals_met = []
    goals_unmet = []
    for goal in goals:
        goal_words = [w.lower() for w in goal.split() if len(w) > 3]
        matches = sum(1 for w in goal_words if w in result_lower)
        if matches >= len(goal_words) * 0.3:
            goals_met.append(goal)
        else:
            goals_unmet.append(goal)

    met_ratio = len(goals_met) / max(len(goals), 1)

    if met_ratio >= 0.5 and len(result.strip()) > 100:
        return {
            "ruling": "RELEASE",
            "confidence": 0.6 + (met_ratio * 0.3),
            "summary": f"Deliverable addresses {len(goals_met)}/{len(goals)} goals. Releasing payment to worker.",
            "reasoning": f"The submitted work ({len(result)} characters) addresses {len(goals_met)} of {len(goals)} stated goals. While not all goals are fully met, the deliverable demonstrates good-faith effort and provides substantive value. The met goals are: {', '.join(goals_met)}. Unmet: {', '.join(goals_unmet) or 'none'}.",
            "goals_met": goals_met,
            "goals_unmet": goals_unmet,
            "recommendation": "For future jobs, workers should explicitly address each goal in their deliverable to avoid disputes.",
        }
    else:
        return {
            "ruling": "REFUND",
            "confidence": 0.6 + ((1 - met_ratio) * 0.3),
            "summary": f"Deliverable addresses only {len(goals_met)}/{len(goals)} goals. Refunding poster.",
            "reasoning": f"The submitted work does not adequately address the job requirements. Only {len(goals_met)} of {len(goals)} goals were met. The unmet goals are: {', '.join(goals_unmet)}. The poster's funds should be refunded.",
            "goals_met": goals_met,
            "goals_unmet": goals_unmet,
            "recommendation": "Workers should carefully review all goals before submitting. Posters should write clear, measurable acceptance criteria.",
        }


async def arbitrate_dispute(job_id: str) -> dict:
    """Arbitrate a disputed job. Returns the ruling and executes it.

    This is the core function — called by the admin endpoint or automated scheduler.
    """
    # Gather all evidence
    job = await db_fetchone(
        "SELECT j.*, a1.agent_name as poster_name, a2.agent_name as worker_name "
        "FROM jobs j JOIN agents a1 ON j.poster_id = a1.agent_id "
        "LEFT JOIN agents a2 ON j.assigned_to = a2.agent_id "
        "WHERE j.job_id = ?", (job_id,),
    )
    if not job:
        raise ValueError("Job not found")
    if job["status"] != "disputed":
        raise ValueError(f"Job is not disputed (status: {job['status']})")

    escrow = await db_fetchone("SELECT * FROM escrow WHERE job_id = ? AND status = 'disputed'", (job_id,))
    if not escrow:
        raise ValueError("No disputed escrow found")

    # Get messages between poster and worker
    messages = []
    if job.get("assigned_to"):
        messages = await db_fetchall(
            "SELECT from_agent_id, subject, body, created_at FROM messages "
            "WHERE (from_agent_id = ? AND to_agent_id = ?) OR (from_agent_id = ? AND to_agent_id = ?) "
            "ORDER BY created_at",
            (job["poster_id"], job["assigned_to"], job["assigned_to"], job["poster_id"]),
        )

    # Try LLM arbitration first
    ruling = None
    if ANTHROPIC_API_KEY:
        evidence = f"""DISPUTED JOB EVIDENCE:

Job Title: {job['title']}
Price: {job['price']} sats
Posted by: {job.get('poster_name', 'unknown')}
Worker: {job.get('worker_name', 'unknown')}

Job Description:
{job['description']}

Goals/Acceptance Criteria:
{json.dumps(json.loads(job['goals']), indent=2)}

Submitted Deliverable:
{job.get('result', '(no deliverable submitted)')[:3000]}

Messages between parties ({len(messages)} total):
{chr(10).join([f"[{m['created_at']}] {m['subject']}: {m['body'][:200]}" for m in messages[:5]])}
"""
        llm_response = await _ask_llm(evidence)
        if llm_response:
            try:
                start = llm_response.find("{")
                end = llm_response.rfind("}") + 1
                if start >= 0 and end > start:
                    ruling = json.loads(llm_response[start:end])
            except (json.JSONDecodeError, ValueError):
                pass

    # Fallback to rule-based
    if not ruling:
        ruling = _rule_based_ruling(job, job["goals"], job.get("result", ""))

    # Execute the ruling
    action = ruling["ruling"].upper()
    def _execute():
        with get_db() as conn:
            if action == "RELEASE":
                release_funds(conn, escrow["escrow_id"])
                conn.execute("UPDATE jobs SET status='completed', updated_at=datetime('now') WHERE job_id=?", (job_id,))
                if job.get("assigned_to"):
                    conn.execute("UPDATE agents SET jobs_completed = jobs_completed + 1 WHERE agent_id = ?", (job["assigned_to"],))
            else:
                refund_funds(conn, escrow["escrow_id"])
                conn.execute("UPDATE jobs SET status='cancelled', updated_at=datetime('now') WHERE job_id=?", (job_id,))

    await asyncio.to_thread(_execute)

    # Log the ruling to the audit trail
    await append_event("arbitration.ruling", "arbitrator", "job", job_id, {
        "ruling": action,
        "confidence": ruling.get("confidence", 0),
        "summary": ruling.get("summary", ""),
        "goals_met": ruling.get("goals_met", []),
        "goals_unmet": ruling.get("goals_unmet", []),
        "method": "llm" if ANTHROPIC_API_KEY and ruling.get("confidence", 0) > 0.7 else "rule_based",
    })

    return {
        "job_id": job_id,
        "job_title": job["title"],
        "poster": job.get("poster_name"),
        "worker": job.get("worker_name"),
        "amount": escrow["amount"],
        **ruling,
        "executed": True,
        "method": "llm" if ANTHROPIC_API_KEY else "rule_based",
    }
