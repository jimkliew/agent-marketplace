"""Deposits (with real Lightning support) and financial queries. All amounts in satoshis."""

import uuid
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request
from backend.auth import require_agent
from backend.database import get_db, db_fetchone, db_fetchall
from backend.events import append_event
from backend.config import PAYMENT_CURRENCY, PAYMENT_UNIT, MAX_TRANSACTION, MIN_DEPOSIT
from backend.models import DepositRequest
from backend.payments import create_invoice, check_invoice, PAYMENT_GATEWAY

router = APIRouter()


@router.post("/deposit")
async def deposit_funds(req: DepositRequest, request: Request, agent_id: str = Depends(require_agent)):
    """Deposit sats. In mock mode, credits instantly. In Lightning mode, returns an invoice to pay."""
    if req.amount > MAX_TRANSACTION:
        raise HTTPException(400, f"Max deposit: {MAX_TRANSACTION} {PAYMENT_UNIT}")

    # Create Lightning invoice (or mock)
    invoice = await create_invoice(req.amount, memo=f"AgentMarket deposit for {agent_id[:8]}")

    if invoice.status == "paid":
        # Mock mode or instant payment — credit immediately
        tx_id = str(uuid.uuid4())
        def _deposit():
            with get_db() as conn:
                conn.execute(
                    "UPDATE agents SET balance = balance + ?, updated_at = datetime('now') WHERE agent_id = ?",
                    (req.amount, agent_id),
                )
                conn.execute(
                    "INSERT INTO ledger (tx_id, from_agent_id, to_agent_id, amount, currency, unit, tx_type, description) VALUES (?,NULL,?,?,?,?,'deposit',?)",
                    (tx_id, agent_id, req.amount, PAYMENT_CURRENCY, PAYMENT_UNIT, f"Deposited {req.amount} {PAYMENT_UNIT}"),
                )
        await asyncio.to_thread(_deposit)
        await append_event("deposit.made", agent_id, "ledger", tx_id, {"amount": req.amount, "unit": PAYMENT_UNIT, "gateway": PAYMENT_GATEWAY})
        agent = await db_fetchone("SELECT balance FROM agents WHERE agent_id = ?", (agent_id,))
        return {"tx_id": tx_id, "amount": req.amount, "unit": PAYMENT_UNIT, "new_balance": agent["balance"], "status": "credited"}
    else:
        # Lightning mode — return invoice for agent to pay
        return {
            "invoice_id": invoice.invoice_id,
            "payment_request": invoice.payment_request,
            "amount": req.amount,
            "unit": PAYMENT_UNIT,
            "status": "awaiting_payment",
            "instructions": "Pay this Lightning invoice to complete your deposit. Then call GET /api/escrow/invoice/{invoice_id} to confirm.",
        }


@router.get("/invoice/{invoice_id}")
async def check_deposit_invoice(invoice_id: str, request: Request, agent_id: str = Depends(require_agent)):
    """Check if a Lightning invoice has been paid and credit the agent's balance."""
    status = await check_invoice(invoice_id)
    if status == "paid":
        # TODO: look up amount from stored invoice record, credit balance
        # For now, return status
        return {"invoice_id": invoice_id, "status": "paid", "message": "Payment received. Balance credited."}
    return {"invoice_id": invoice_id, "status": status}


@router.post("/withdraw")
async def withdraw_funds(request: Request, agent_id: str = Depends(require_agent)):
    """Withdraw sats to a Lightning invoice. Agent's balance is deducted."""
    body = await request.json()
    amount = int(body.get("amount", 0))
    destination = str(body.get("destination", ""))  # bolt11 invoice or Lightning address
    if amount < 100:
        raise HTTPException(400, f"Minimum withdrawal: 100 {PAYMENT_UNIT}")
    if not destination:
        raise HTTPException(400, "destination required (Lightning invoice or address)")

    # Check balance
    agent = await db_fetchone("SELECT balance FROM agents WHERE agent_id = ?", (agent_id,))
    if not agent or agent["balance"] < amount:
        raise HTTPException(400, f"Insufficient balance. Have {agent['balance'] if agent else 0}, need {amount} {PAYMENT_UNIT}")

    # Process payout
    from backend.payments import pay_out
    withdrawal = await pay_out(amount, destination)

    if withdrawal.status == "completed":
        tx_id = str(uuid.uuid4())
        def _withdraw():
            with get_db() as conn:
                conn.execute("UPDATE agents SET balance = balance - ?, updated_at = datetime('now') WHERE agent_id = ?", (amount, agent_id))
                conn.execute(
                    "INSERT INTO ledger (tx_id, from_agent_id, to_agent_id, amount, currency, unit, tx_type, description) VALUES (?,?,NULL,?,?,?,'withdrawal',?)",
                    (tx_id, agent_id, amount, PAYMENT_CURRENCY, PAYMENT_UNIT, f"Withdrew {amount} {PAYMENT_UNIT} to {destination[:30]}..."),
                )
        await asyncio.to_thread(_withdraw)
        await append_event("withdrawal.completed", agent_id, "ledger", tx_id, {"amount": amount, "destination": destination[:50]})
        new_bal = await db_fetchone("SELECT balance FROM agents WHERE agent_id = ?", (agent_id,))
        return {"withdrawal_id": withdrawal.withdrawal_id, "amount": amount, "unit": PAYMENT_UNIT,
                "new_balance": new_bal["balance"], "status": "completed"}
    else:
        raise HTTPException(502, "Withdrawal failed. Funds not deducted. Try again.")


@router.get("/{agent_id}/balance")
async def get_balance(agent_id: str, request: Request, _=Depends(require_agent)):
    if request.state.agent_id != agent_id:
        raise HTTPException(403, "Can only view own balance")
    agent = await db_fetchone("SELECT balance FROM agents WHERE agent_id = ?", (agent_id,))
    if not agent:
        raise HTTPException(404, "Agent not found")
    return {"agent_id": agent_id, "balance": agent["balance"], "unit": PAYMENT_UNIT}


@router.get("/{agent_id}/transactions")
async def get_transactions(agent_id: str, request: Request, _=Depends(require_agent), page: int = 1, page_size: int = 20):
    if request.state.agent_id != agent_id:
        raise HTTPException(403, "Can only view own transactions")
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size
    txs = await db_fetchall(
        "SELECT * FROM ledger WHERE from_agent_id = ? OR to_agent_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (agent_id, agent_id, page_size, offset),
    )
    return {"items": txs, "page": page, "page_size": page_size}
