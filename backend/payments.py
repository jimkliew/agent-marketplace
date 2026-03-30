"""Payment gateway — abstracts real Bitcoin/Lightning payments.

Supports multiple backends:
  - "mock"   : Internal ledger only (default, for testing)
  - "strike" : Strike API (real Lightning payments, custodial)
  - "lnbits" : LNbits (self-hosted Lightning, non-custodial)

Set PAYMENT_GATEWAY in .env to switch between backends.
All amounts in satoshis.
"""

import os
import uuid
import httpx
from dataclasses import dataclass

PAYMENT_GATEWAY = os.getenv("PAYMENT_GATEWAY", "mock")
STRIKE_API_KEY = os.getenv("STRIKE_API_KEY", "")
LNBITS_URL = os.getenv("LNBITS_URL", "")
LNBITS_API_KEY = os.getenv("LNBITS_API_KEY", "")


@dataclass
class Invoice:
    invoice_id: str
    payment_request: str  # Lightning invoice (bolt11) or on-chain address
    amount_sats: int
    status: str  # "pending", "paid", "expired"
    gateway: str


@dataclass
class Withdrawal:
    withdrawal_id: str
    amount_sats: int
    destination: str  # Lightning address or bolt11 invoice
    status: str  # "pending", "completed", "failed"
    gateway: str


# === Mock Gateway (for testing / internal ledger) ===

async def mock_create_invoice(amount_sats: int, memo: str = "") -> Invoice:
    """Create a mock invoice — auto-marks as paid for testing."""
    return Invoice(
        invoice_id=str(uuid.uuid4()),
        payment_request=f"lnbc{amount_sats}mock_{uuid.uuid4().hex[:16]}",
        amount_sats=amount_sats,
        status="paid",  # Auto-paid in mock mode
        gateway="mock",
    )


async def mock_check_invoice(invoice_id: str) -> str:
    return "paid"


async def mock_withdraw(amount_sats: int, destination: str) -> Withdrawal:
    return Withdrawal(
        withdrawal_id=str(uuid.uuid4()),
        amount_sats=amount_sats,
        destination=destination,
        status="completed",
        gateway="mock",
    )


# === Strike API Gateway (real Lightning) ===

async def strike_create_invoice(amount_sats: int, memo: str = "") -> Invoice:
    """Create a Lightning invoice via Strike API."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.strike.me/v1/invoices",
            headers={"Authorization": f"Bearer {STRIKE_API_KEY}", "Content-Type": "application/json"},
            json={
                "correlationId": str(uuid.uuid4()),
                "description": memo or "AgentMarket deposit",
                "amount": {"amount": str(amount_sats / 100_000_000), "currency": "BTC"},
            },
        )
        r.raise_for_status()
        data = r.json()
        invoice_id = data["invoiceId"]

        # Get the Lightning invoice string
        r2 = await client.post(
            f"https://api.strike.me/v1/invoices/{invoice_id}/quote",
            headers={"Authorization": f"Bearer {STRIKE_API_KEY}"},
        )
        r2.raise_for_status()
        quote = r2.json()

        return Invoice(
            invoice_id=invoice_id,
            payment_request=quote.get("lnInvoice", ""),
            amount_sats=amount_sats,
            status="pending",
            gateway="strike",
        )


async def strike_check_invoice(invoice_id: str) -> str:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"https://api.strike.me/v1/invoices/{invoice_id}",
            headers={"Authorization": f"Bearer {STRIKE_API_KEY}"},
        )
        r.raise_for_status()
        state = r.json()["state"]
        return {"UNPAID": "pending", "PENDING": "pending", "PAID": "paid", "CANCELLED": "expired"}.get(state, "pending")


# === LNbits Gateway (self-hosted Lightning) ===

async def lnbits_create_invoice(amount_sats: int, memo: str = "") -> Invoice:
    """Create a Lightning invoice via LNbits."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{LNBITS_URL}/api/v1/payments",
            headers={"X-Api-Key": LNBITS_API_KEY, "Content-Type": "application/json"},
            json={"out": False, "amount": amount_sats, "memo": memo or "AgentMarket deposit"},
        )
        r.raise_for_status()
        data = r.json()
        return Invoice(
            invoice_id=data["payment_hash"],
            payment_request=data["payment_request"],
            amount_sats=amount_sats,
            status="pending",
            gateway="lnbits",
        )


async def lnbits_check_invoice(invoice_id: str) -> str:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{LNBITS_URL}/api/v1/payments/{invoice_id}",
            headers={"X-Api-Key": LNBITS_API_KEY},
        )
        r.raise_for_status()
        return "paid" if r.json().get("paid") else "pending"


# === Gateway Router ===

async def create_invoice(amount_sats: int, memo: str = "") -> Invoice:
    """Create a payment invoice using the configured gateway."""
    if PAYMENT_GATEWAY == "strike":
        return await strike_create_invoice(amount_sats, memo)
    elif PAYMENT_GATEWAY == "lnbits":
        return await lnbits_create_invoice(amount_sats, memo)
    else:
        return await mock_create_invoice(amount_sats, memo)


async def check_invoice(invoice_id: str) -> str:
    """Check payment status. Returns: 'pending', 'paid', or 'expired'."""
    if PAYMENT_GATEWAY == "strike":
        return await strike_check_invoice(invoice_id)
    elif PAYMENT_GATEWAY == "lnbits":
        return await lnbits_check_invoice(invoice_id)
    else:
        return await mock_check_invoice(invoice_id)


async def pay_out(amount_sats: int, destination: str) -> Withdrawal:
    """Pay out sats to a Lightning address/invoice. Used for agent withdrawals."""
    if PAYMENT_GATEWAY == "strike":
        # Strike pay-out via Lightning invoice
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.patch(
                "https://api.strike.me/v1/payment-quotes/lightning",
                headers={"Authorization": f"Bearer {STRIKE_API_KEY}", "Content-Type": "application/json"},
                json={"lnInvoice": destination, "sourceCurrency": "BTC"},
            )
            status = "completed" if r.status_code == 200 else "failed"
            return Withdrawal(str(uuid.uuid4()), amount_sats, destination, status, "strike")
    elif PAYMENT_GATEWAY == "lnbits":
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{LNBITS_URL}/api/v1/payments",
                headers={"X-Api-Key": LNBITS_API_KEY, "Content-Type": "application/json"},
                json={"out": True, "bolt11": destination},
            )
            status = "completed" if r.status_code in (200, 201) else "failed"
            return Withdrawal(str(uuid.uuid4()), amount_sats, destination, status, "lnbits")
    else:
        return await mock_withdraw(amount_sats, destination)
