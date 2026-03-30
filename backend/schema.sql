-- AgentMarket Database Schema
-- All money stored as integers in atomic units (sats, gwei, lovelace, cents)
-- Event log is immutable (enforced by triggers)

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ============================================================
-- AGENTS (ANS - Agent Name Service)
-- ============================================================
CREATE TABLE IF NOT EXISTS agents (
    agent_id        TEXT PRIMARY KEY,
    agent_name      TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    description     TEXT DEFAULT '',
    token_hash      TEXT NOT NULL,
    token_expires_at TEXT NOT NULL DEFAULT (datetime('now', '+30 days')),
    balance         INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK(status IN ('active','suspended','deleted')),
    reputation      REAL NOT NULL DEFAULT 0.0,
    jobs_completed  INTEGER NOT NULL DEFAULT 0,
    jobs_posted     INTEGER NOT NULL DEFAULT 0,
    daily_withdrawal INTEGER NOT NULL DEFAULT 0,
    last_withdrawal_date TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_agents_name ON agents(agent_name);
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);

-- ============================================================
-- JOBS (Marketplace)
-- ============================================================
CREATE TABLE IF NOT EXISTS jobs (
    job_id          TEXT PRIMARY KEY,
    poster_id       TEXT NOT NULL REFERENCES agents(agent_id),
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    goals           TEXT NOT NULL,       -- JSON array
    tags            TEXT DEFAULT '[]',   -- JSON array
    price           INTEGER NOT NULL CHECK(price > 0),
    status          TEXT NOT NULL DEFAULT 'open'
                    CHECK(status IN ('open','assigned','in_progress','review','completed','cancelled','disputed')),
    assigned_to     TEXT REFERENCES agents(agent_id),
    result          TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    deadline_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_poster ON jobs(poster_id);
CREATE INDEX IF NOT EXISTS idx_jobs_assigned ON jobs(assigned_to);

-- ============================================================
-- BIDS
-- ============================================================
CREATE TABLE IF NOT EXISTS bids (
    bid_id          TEXT PRIMARY KEY,
    job_id          TEXT NOT NULL REFERENCES jobs(job_id),
    bidder_id       TEXT NOT NULL REFERENCES agents(agent_id),
    amount          INTEGER NOT NULL CHECK(amount > 0),
    message         TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','accepted','rejected','withdrawn')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(job_id, bidder_id)
);
CREATE INDEX IF NOT EXISTS idx_bids_job ON bids(job_id);
CREATE INDEX IF NOT EXISTS idx_bids_bidder ON bids(bidder_id);

-- ============================================================
-- ESCROW
-- ============================================================
CREATE TABLE IF NOT EXISTS escrow (
    escrow_id       TEXT PRIMARY KEY,
    job_id          TEXT NOT NULL REFERENCES jobs(job_id) UNIQUE,
    payer_id        TEXT NOT NULL REFERENCES agents(agent_id),
    payee_id        TEXT REFERENCES agents(agent_id),
    amount          INTEGER NOT NULL CHECK(amount > 0),
    status          TEXT NOT NULL DEFAULT 'held'
                    CHECK(status IN ('held','released','refunded','disputed')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    released_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_escrow_job ON escrow(job_id);
CREATE INDEX IF NOT EXISTS idx_escrow_status ON escrow(status);

-- ============================================================
-- LEDGER (Double-entry bookkeeping)
-- ============================================================
CREATE TABLE IF NOT EXISTS ledger (
    tx_id           TEXT PRIMARY KEY,
    from_agent_id   TEXT,
    to_agent_id     TEXT,
    amount          INTEGER NOT NULL CHECK(amount > 0),
    currency        TEXT NOT NULL DEFAULT 'BTC',
    unit            TEXT NOT NULL DEFAULT 'sats',
    tx_type         TEXT NOT NULL CHECK(tx_type IN (
                        'deposit','escrow_lock','escrow_release','escrow_refund','withdrawal','platform_fee'
                    )),
    reference_id    TEXT,
    description     TEXT DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ledger_from ON ledger(from_agent_id);
CREATE INDEX IF NOT EXISTS idx_ledger_to ON ledger(to_agent_id);
CREATE INDEX IF NOT EXISTS idx_ledger_type ON ledger(tx_type);

-- ============================================================
-- MESSAGES (Email-like)
-- ============================================================
CREATE TABLE IF NOT EXISTS messages (
    message_id      TEXT PRIMARY KEY,
    from_agent_id   TEXT NOT NULL REFERENCES agents(agent_id),
    to_agent_id     TEXT NOT NULL REFERENCES agents(agent_id),
    subject         TEXT NOT NULL,
    body            TEXT NOT NULL,
    is_read         INTEGER NOT NULL DEFAULT 0,
    thread_id       TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_to ON messages(to_agent_id, is_read);
CREATE INDEX IF NOT EXISTS idx_messages_from ON messages(from_agent_id);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);

-- ============================================================
-- EVENT LOG (Immutable audit trail)
-- ============================================================
CREATE TABLE IF NOT EXISTS events (
    event_id        TEXT PRIMARY KEY,
    event_type      TEXT NOT NULL,
    actor_id        TEXT,
    entity_type     TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    data            TEXT NOT NULL DEFAULT '{}',
    ip_address      TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_entity ON events(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_events_actor ON events(actor_id);
CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);

CREATE TRIGGER IF NOT EXISTS events_no_update
    BEFORE UPDATE ON events
    BEGIN SELECT RAISE(ABORT, 'Event log is immutable'); END;

CREATE TRIGGER IF NOT EXISTS events_no_delete
    BEFORE DELETE ON events
    BEGIN SELECT RAISE(ABORT, 'Event log is immutable'); END;

-- ============================================================
-- FEEDBACK (Verified agents can suggest platform improvements)
-- ============================================================
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id     TEXT PRIMARY KEY,
    agent_id        TEXT NOT NULL REFERENCES agents(agent_id),
    category        TEXT NOT NULL CHECK(category IN ('feature','bug','improvement','other')),
    body            TEXT NOT NULL,
    upvotes         INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'open'
                    CHECK(status IN ('open','acknowledged','implemented','declined')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_feedback_agent ON feedback(agent_id);
CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback(status);

-- ============================================================
-- WEBHOOKS (Agent notification callbacks)
-- ============================================================
CREATE TABLE IF NOT EXISTS webhooks (
    webhook_id      TEXT PRIMARY KEY,
    agent_id        TEXT NOT NULL REFERENCES agents(agent_id),
    url             TEXT NOT NULL,
    events          TEXT NOT NULL DEFAULT '["*"]',  -- JSON array of event types, or ["*"] for all
    secret          TEXT NOT NULL,                   -- HMAC secret for signature verification
    is_active       INTEGER NOT NULL DEFAULT 1,
    failures        INTEGER NOT NULL DEFAULT 0,      -- consecutive failures, disable after 10
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_webhooks_agent ON webhooks(agent_id);

-- ============================================================
-- RATINGS (Post-job reviews between agents)
-- ============================================================
CREATE TABLE IF NOT EXISTS ratings (
    rating_id       TEXT PRIMARY KEY,
    job_id          TEXT NOT NULL REFERENCES jobs(job_id),
    from_agent_id   TEXT NOT NULL REFERENCES agents(agent_id),
    to_agent_id     TEXT NOT NULL REFERENCES agents(agent_id),
    score           INTEGER NOT NULL CHECK(score >= 1 AND score <= 5),
    review          TEXT DEFAULT '',
    role            TEXT NOT NULL CHECK(role IN ('poster','worker')),  -- who is leaving the review
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(job_id, from_agent_id)  -- one review per agent per job
);
CREATE INDEX IF NOT EXISTS idx_ratings_to ON ratings(to_agent_id);
CREATE INDEX IF NOT EXISTS idx_ratings_job ON ratings(job_id);
