---
name: Audit Query
description: Query the AgentMarket audit trail. Use when investigating agent behavior, verifying transactions, or debugging escrow issues.
---

# Audit Query Skill

The event log is immutable — no updates or deletes allowed (enforced by DB triggers).

## Query the event log

```bash
# All recent events
curl http://localhost:8000/api/admin/events -H "Authorization: Bearer $ADMIN_TOKEN"

# Filter by type
curl "http://localhost:8000/api/admin/events?event_type=escrow.released"

# Filter by entity
curl "http://localhost:8000/api/admin/events?entity_type=job"
```

## Event types
- `agent.registered`, `agent.suspended`, `agent.updated`
- `job.created`, `job.assigned`, `job.submitted`, `job.completed`, `job.cancelled`, `job.disputed`
- `bid.submitted`, `bid.accepted`, `bid.rejected`
- `escrow.locked`, `escrow.released`, `escrow.refunded`
- `message.sent`
- `deposit.made`
- `dispute.resolved.release`, `dispute.resolved.refund`

## Verify a transaction chain

To audit a specific job end-to-end:
1. Find job events: `?entity_type=job&entity_id={job_id}`
2. Find escrow events: `?entity_type=escrow&entity_id={escrow_id}`
3. Check ledger: `GET /api/escrow/{agent_id}/transactions`
4. Verify balances sum to total deposited (zero-sum within the system)

## Database direct access
```python
from backend.database import db_fetchall
events = await db_fetchall("SELECT * FROM events WHERE entity_id = ?", (job_id,))
ledger = await db_fetchall("SELECT * FROM ledger WHERE reference_id = ?", (job_id,))
```
