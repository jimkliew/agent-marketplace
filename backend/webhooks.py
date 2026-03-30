"""Webhook system — push notifications to agents via HTTP callbacks.

Agents register a URL and get POST requests when events happen:
  - bid.received      — someone bid on your job
  - job.assigned      — your bid was accepted
  - work.submitted    — worker delivered on your job
  - payment.released  — you got paid
  - message.received  — new message in your inbox

Each webhook is signed with HMAC-SHA256 so agents can verify authenticity.
"""

import hmac
import hashlib
import json
import uuid
import asyncio
import httpx
from backend.database import get_db, db_fetchall


async def get_agent_webhooks(agent_id: str) -> list[dict]:
    """Get all active webhooks for an agent."""
    return await db_fetchall(
        "SELECT * FROM webhooks WHERE agent_id = ? AND is_active = 1",
        (agent_id,),
    )


def _sign_payload(payload: str, secret: str) -> str:
    """Create HMAC-SHA256 signature for webhook payload."""
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


async def fire_webhook(agent_id: str, event_type: str, data: dict):
    """Send webhook notification to an agent. Non-blocking, fire-and-forget."""
    hooks = await get_agent_webhooks(agent_id)
    if not hooks:
        return

    payload = json.dumps({"event": event_type, "data": data, "timestamp": str(uuid.uuid4())})

    async def _send(hook: dict):
        try:
            events_filter = json.loads(hook.get("events", '["*"]'))
            if "*" not in events_filter and event_type not in events_filter:
                return  # Agent doesn't want this event type

            signature = _sign_payload(payload, hook["secret"])
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.post(
                    hook["url"],
                    content=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-AgentMarket-Signature": signature,
                        "X-AgentMarket-Event": event_type,
                    },
                )
                if r.status_code >= 400:
                    _increment_failure(hook["webhook_id"])
                else:
                    _reset_failure(hook["webhook_id"])
        except Exception:
            _increment_failure(hook["webhook_id"])

    # Fire all hooks in parallel, non-blocking
    tasks = [_send(hook) for hook in hooks]
    if tasks:
        asyncio.gather(*tasks, return_exceptions=True)


def _increment_failure(webhook_id: str):
    """Increment failure count. Disable after 10 consecutive failures."""
    try:
        with get_db() as conn:
            conn.execute("UPDATE webhooks SET failures = failures + 1 WHERE webhook_id = ?", (webhook_id,))
            conn.execute("UPDATE webhooks SET is_active = 0 WHERE webhook_id = ? AND failures >= 10", (webhook_id,))
    except Exception:
        pass


def _reset_failure(webhook_id: str):
    """Reset failure count on successful delivery."""
    try:
        with get_db() as conn:
            conn.execute("UPDATE webhooks SET failures = 0 WHERE webhook_id = ?", (webhook_id,))
    except Exception:
        pass
