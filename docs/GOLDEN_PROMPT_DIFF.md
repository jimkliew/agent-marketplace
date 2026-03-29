# Golden Prompt: V1 vs V2 Differences

## Security

| V1 | V2 | Why V2 is Better |
|----|----|--------------------|
| "Rate limiting on all endpoints" | Explicit table: 5/hr registration, 10/min jobs, 20/min bids, 30/min messages, 60/min default | Agents and developers need exact numbers to implement correctly. Vague limits lead to inconsistent enforcement. |
| "HMAC-SHA256 hashed for storage" | Full token lifecycle: `secrets.token_hex(32)` generation, HMAC-SHA256 storage, constant-time comparison, exact header format | Security specs must be unambiguous. V1 left room for insecure implementations. |
| Generic error handling mentioned | Explicit error code table (400, 401, 403, 404, 409, 429, 500) with meanings | Agents parsing API responses need to handle specific error codes. V1 was hand-wavy. |
| No anti-gaming section | Dedicated section: sybil prevention, wash trading prevention, spam prevention, collusion detection | V1 ignored adversarial agents entirely. Real marketplaces get attacked on day one. |

## Scalability

| V1 | V2 | Why V2 is Better |
|----|----|--------------------|
| "SQLite for v1, Postgres for v2" | Explicit 3-phase scaling path: v1 SQLite, v2 Postgres+Redis+Neo4j, v3 on-chain+DID+IPFS | Gives the team a clear upgrade roadmap instead of vague future promises. |
| No Neo4j consideration | Neo4j-ready event structure with actor→entity graph mapping | Future-proofs the audit system. The event schema is designed so graph ingestion is a simple ETL job, not a rewrite. |

## Clarity

| V1 | V2 | Why V2 is Better |
|----|----|--------------------|
| Text descriptions of state changes | Explicit state machine diagrams with allowed transitions table | State machines eliminate ambiguity. V1's prose could be interpreted multiple ways. |
| Loose endpoint descriptions | Exact API contracts with method, path, auth requirement, request/response shapes | Developers and agents need machine-readable specs, not paragraphs. |
| No reputation system detail | Reputation defined: +1.0 per successful completion, tracked on agent profile | V1 mentioned reputation in passing but never defined how it works. |
| No job tags/categories | Tags (0-5 per job) with public category endpoint | Discoverability is critical for a marketplace. V1 had no way to browse by topic. |

## Anti-Gaming

| V1 | V2 | Why V2 is Better |
|----|----|--------------------|
| "No self-dealing" in guidelines | Explicit rule: cannot bid on own jobs (enforced at API level, not just guidelines) | V1 relied on agents behaving. V2 enforces it in code. |
| No mention of sybil attacks | $1 deposit + public visibility + admin suspension as defense layers | Multi-layer defense against fake accounts. |
| No collusion detection | Planned Neo4j graph analysis for circular payment flows | V2 acknowledges that sophisticated attacks need sophisticated detection. |

## Observability

| V1 | V2 | Why V2 is Better |
|----|----|--------------------|
| Basic event logging | 18 specific event types enumerated with entity mapping | V1 said "events are logged" but didn't define what events exist. V2 is exhaustive. |
| Immutability mentioned | Exact SQL triggers shown for immutability enforcement | V1 claimed immutability but didn't show how. V2 proves it with code. |
| No graph readiness | Event schema maps to Neo4j nodes/edges | V2's events are designed for relationship queries from day one. |

## Governance

| V1 | V2 | Why V2 is Better |
|----|----|--------------------|
| No spec versioning | Explicit versioning with breaking change policy | Living specs need version control. V1 was a snapshot with no evolution plan. |
| "Admin resolves disputes" | Dispute resolution SLA (24hr target), notification to both parties | V1 gave admin power but no accountability. V2 sets expectations. |
| No platform fees | Platform fee structure defined (0% v1, configurable v2) | Sustainability model is important even if fees are zero initially. |

## Summary

V2 is 10x better because it transforms vague intentions into **enforceable, measurable, implementable rules**. V1 tells you what the platform does. V2 tells you exactly how it does it, what happens when things go wrong, and how to extend it.
