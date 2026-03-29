"""Escrow — lock, release, refund. All amounts in satoshis. Platform fee on release."""

import uuid
import sqlite3
from backend.config import PAYMENT_CURRENCY, PAYMENT_UNIT, PLATFORM_FEE_BPS


def _calc_fee(amount: int) -> int:
    """Calculate platform fee. 50 bps = 0.50%. Minimum 0 sats (no fee on tiny amounts)."""
    return (amount * PLATFORM_FEE_BPS) // 10_000


def lock_funds(conn: sqlite3.Connection, payer_id: str, job_id: str, amount: int) -> str:
    """Lock sats in escrow when a job is posted. Returns escrow_id."""
    agent = conn.execute("SELECT balance FROM agents WHERE agent_id = ?", (payer_id,)).fetchone()
    if not agent or agent["balance"] < amount:
        raise ValueError(f"Insufficient balance. Need {amount} {PAYMENT_UNIT}, have {agent['balance'] if agent else 0}")
    escrow_id = str(uuid.uuid4())
    tx_id = str(uuid.uuid4())
    conn.execute("UPDATE agents SET balance = balance - ?, updated_at = datetime('now') WHERE agent_id = ?", (amount, payer_id))
    conn.execute("INSERT INTO escrow (escrow_id, job_id, payer_id, amount, status) VALUES (?,?,?,?,'held')", (escrow_id, job_id, payer_id, amount))
    conn.execute(
        "INSERT INTO ledger (tx_id, from_agent_id, to_agent_id, amount, currency, unit, tx_type, reference_id, description) VALUES (?,?,NULL,?,?,?,'escrow_lock',?,?)",
        (tx_id, payer_id, amount, PAYMENT_CURRENCY, PAYMENT_UNIT, job_id, f"Locked {amount} {PAYMENT_UNIT} in escrow"),
    )
    return escrow_id


def release_funds(conn: sqlite3.Connection, escrow_id: str) -> dict:
    """Release escrowed sats to worker minus platform fee. Returns {worker_amount, fee_amount}."""
    row = conn.execute("SELECT * FROM escrow WHERE escrow_id = ? AND status = 'held'", (escrow_id,)).fetchone()
    if not row:
        raise ValueError("Escrow not found or not in held status")
    if not row["payee_id"]:
        raise ValueError("No payee assigned")
    escrow = dict(row)

    fee = _calc_fee(escrow["amount"])
    worker_amount = escrow["amount"] - fee

    # Credit worker (amount minus fee)
    conn.execute("UPDATE agents SET balance = balance + ?, updated_at = datetime('now') WHERE agent_id = ?", (worker_amount, escrow["payee_id"]))
    conn.execute("UPDATE escrow SET status = 'released', released_at = datetime('now') WHERE escrow_id = ?", (escrow_id,))

    # Ledger: worker payment
    tx_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO ledger (tx_id, from_agent_id, to_agent_id, amount, currency, unit, tx_type, reference_id, description) VALUES (?,NULL,?,?,?,?,'escrow_release',?,?)",
        (tx_id, escrow["payee_id"], worker_amount, PAYMENT_CURRENCY, PAYMENT_UNIT, escrow["job_id"],
         f"Released {worker_amount} {PAYMENT_UNIT} to worker (gross {escrow['amount']}, fee {fee})"),
    )

    # Ledger: platform fee (if any)
    if fee > 0:
        fee_tx_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO ledger (tx_id, from_agent_id, to_agent_id, amount, currency, unit, tx_type, reference_id, description) VALUES (?,NULL,NULL,?,?,?,'platform_fee',?,?)",
            (fee_tx_id, fee, PAYMENT_CURRENCY, PAYMENT_UNIT, escrow["job_id"],
             f"Platform fee {PLATFORM_FEE_BPS}bps on {escrow['amount']} {PAYMENT_UNIT}"),
        )

    return {"worker_amount": worker_amount, "fee_amount": fee, "gross_amount": escrow["amount"]}


def refund_funds(conn: sqlite3.Connection, escrow_id: str) -> bool:
    """Refund escrowed sats to poster. Full refund, no fee on refunds."""
    row = conn.execute("SELECT * FROM escrow WHERE escrow_id = ? AND status IN ('held','disputed')", (escrow_id,)).fetchone()
    if not row:
        raise ValueError("Escrow not found or not refundable")
    escrow = dict(row)
    tx_id = str(uuid.uuid4())
    conn.execute("UPDATE agents SET balance = balance + ?, updated_at = datetime('now') WHERE agent_id = ?", (escrow["amount"], escrow["payer_id"]))
    conn.execute("UPDATE escrow SET status = 'refunded', released_at = datetime('now') WHERE escrow_id = ?", (escrow_id,))
    conn.execute(
        "INSERT INTO ledger (tx_id, from_agent_id, to_agent_id, amount, currency, unit, tx_type, reference_id, description) VALUES (?,NULL,?,?,?,?,'escrow_refund',?,?)",
        (tx_id, escrow["payer_id"], escrow["amount"], PAYMENT_CURRENCY, PAYMENT_UNIT, escrow["job_id"], f"Refunded {escrow['amount']} {PAYMENT_UNIT} to poster"),
    )
    return True
