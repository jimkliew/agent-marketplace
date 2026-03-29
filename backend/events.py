"""Immutable event log — append-only audit trail."""

import json
import uuid
import asyncio
from backend.database import get_db


async def append_event(
    event_type: str,
    actor_id: str | None,
    entity_type: str,
    entity_id: str,
    data: dict | None = None,
    ip_address: str | None = None,
) -> str:
    event_id = str(uuid.uuid4())
    def _insert():
        with get_db() as conn:
            conn.execute(
                "INSERT INTO events (event_id, event_type, actor_id, entity_type, entity_id, data, ip_address) VALUES (?,?,?,?,?,?,?)",
                (event_id, event_type, actor_id, entity_type, entity_id, json.dumps(data or {}), ip_address),
            )
    await asyncio.to_thread(_insert)
    return event_id


async def query_events(
    event_type: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    conditions, params = [], []
    if event_type:
        conditions.append("event_type = ?"); params.append(event_type)
    if entity_type:
        conditions.append("entity_type = ?"); params.append(entity_type)
    if entity_id:
        conditions.append("entity_id = ?"); params.append(entity_id)
    if actor_id:
        conditions.append("actor_id = ?"); params.append(actor_id)
    where = " AND ".join(conditions) if conditions else "1=1"
    params.extend([limit, offset])
    def _query():
        with get_db() as conn:
            rows = conn.execute(
                f"SELECT * FROM events WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                tuple(params),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["data"] = json.loads(d["data"])
                result.append(d)
            return result
    return await asyncio.to_thread(_query)
