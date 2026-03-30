"""
AgentMarket Wallet Integration — three ways to fund your agent.

Phase 1: Admin credits (testing/onboarding — no real sats)
Phase 2: External wallet (Alby, LNbits — agent has API key to a Lightning wallet)
Phase 3: Self-sovereign (agent generates its own keypair, controls its own sats)

Phase 3 is the goal. An agent that can hold, send, and receive Bitcoin
without any third party is a fully autonomous economic actor.
"""

import os
import httpx


class MockWallet:
    """Phase 1: No real sats. Platform credits balance via admin endpoint.
    Good for testing and onboarding. Not real money."""

    def __init__(self):
        self.name = "mock"

    async def pay_invoice(self, bolt11: str, amount_sats: int) -> dict:
        return {"status": "mock_paid", "note": "No real sats moved. Use Phase 2 or 3 for real payments."}


class AlbyWallet:
    """Phase 2: Alby Lightning wallet. Agent holds an Alby API key.

    Setup:
        1. Go to https://getalby.com and create an account
        2. Go to Developer → API Keys → Create new key
        3. Set ALBY_API_KEY environment variable

    The agent can programmatically pay Lightning invoices.
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.getenv("ALBY_API_KEY", "")
        self.name = "alby"
        if not self.api_key:
            raise ValueError("ALBY_API_KEY required. Get one at https://getalby.com")

    async def pay_invoice(self, bolt11: str, amount_sats: int) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.getalby.com/payments/bolt11",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"invoice": bolt11},
            )
            if r.status_code in (200, 201):
                return {"status": "paid", "gateway": "alby", "data": r.json()}
            return {"status": "failed", "error": r.text}

    async def get_balance(self) -> int:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.getalby.com/balance",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            if r.status_code == 200:
                return r.json().get("balance", 0)
            return 0

    async def create_invoice(self, amount_sats: int, memo: str = "") -> str:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://api.getalby.com/invoices",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"amount": amount_sats, "description": memo or "AgentMarket withdrawal"},
            )
            if r.status_code in (200, 201):
                return r.json().get("payment_request", "")
            return ""


class LNbitsWallet:
    """Phase 2 (self-hosted): LNbits wallet. You run your own Lightning node.

    Setup:
        1. Install LNbits (https://lnbits.com) or use a hosted instance
        2. Create a wallet, get the Admin API key
        3. Set LNBITS_URL and LNBITS_API_KEY environment variables
    """

    def __init__(self, url: str = "", api_key: str = ""):
        self.url = (url or os.getenv("LNBITS_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("LNBITS_API_KEY", "")
        self.name = "lnbits"
        if not self.url or not self.api_key:
            raise ValueError("LNBITS_URL and LNBITS_API_KEY required")

    async def pay_invoice(self, bolt11: str, amount_sats: int) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{self.url}/api/v1/payments",
                headers={"X-Api-Key": self.api_key, "Content-Type": "application/json"},
                json={"out": True, "bolt11": bolt11},
            )
            if r.status_code in (200, 201):
                return {"status": "paid", "gateway": "lnbits", "data": r.json()}
            return {"status": "failed", "error": r.text}

    async def get_balance(self) -> int:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{self.url}/api/v1/wallet",
                headers={"X-Api-Key": self.api_key},
            )
            if r.status_code == 200:
                return r.json().get("balance", 0) // 1000  # LNbits returns millisats
            return 0


class SovereignWallet:
    """Phase 3: Agent controls its own Bitcoin. No third party.

    The agent generates or imports a seed phrase, derives Lightning keys,
    and can send/receive sats autonomously. This is the endgame for
    agent-to-agent commerce — fully self-sovereign economic actors.

    Implementation options:
        a) Wrapped LND node (agent runs its own Lightning node)
        b) Breez SDK (embedded Lightning, no node management)
        c) Greenlight (CLN in the cloud, agent holds keys)
        d) LDK (Lightning Dev Kit — build custom Lightning into the agent)

    For now, this wraps an LND REST API. The agent operator runs LND
    and gives the agent the macaroon + endpoint.
    """

    def __init__(self, lnd_url: str = "", macaroon: str = ""):
        self.lnd_url = (lnd_url or os.getenv("LND_REST_URL", "")).rstrip("/")
        self.macaroon = macaroon or os.getenv("LND_MACAROON", "")
        self.name = "sovereign"
        if not self.lnd_url or not self.macaroon:
            raise ValueError(
                "LND_REST_URL and LND_MACAROON required for sovereign wallet. "
                "Run your own LND node or use Voltage (https://voltage.cloud)."
            )

    async def pay_invoice(self, bolt11: str, amount_sats: int) -> dict:
        async with httpx.AsyncClient(timeout=30, verify=False) as client:
            r = await client.post(
                f"{self.lnd_url}/v1/channels/transactions",
                headers={"Grpc-Metadata-macaroon": self.macaroon},
                json={"payment_request": bolt11},
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("payment_error") == "":
                    return {"status": "paid", "gateway": "lnd", "preimage": data.get("payment_preimage")}
                return {"status": "failed", "error": data.get("payment_error")}
            return {"status": "failed", "error": r.text}

    async def get_balance(self) -> int:
        async with httpx.AsyncClient(timeout=10, verify=False) as client:
            r = await client.get(
                f"{self.lnd_url}/v1/balance/channels",
                headers={"Grpc-Metadata-macaroon": self.macaroon},
            )
            if r.status_code == 200:
                return int(r.json().get("balance", 0))
            return 0

    async def create_invoice(self, amount_sats: int, memo: str = "") -> str:
        async with httpx.AsyncClient(timeout=10, verify=False) as client:
            r = await client.post(
                f"{self.lnd_url}/v1/invoices",
                headers={"Grpc-Metadata-macaroon": self.macaroon},
                json={"value": amount_sats, "memo": memo or "AgentMarket"},
            )
            if r.status_code == 200:
                return r.json().get("payment_request", "")
            return ""


def get_wallet(wallet_type: str = "", **kwargs):
    """Factory: get the right wallet based on configuration.

    Usage:
        wallet = get_wallet("alby", api_key="...")
        wallet = get_wallet("lnbits", url="...", api_key="...")
        wallet = get_wallet("sovereign", lnd_url="...", macaroon="...")
        wallet = get_wallet("mock")  # testing
        wallet = get_wallet()  # auto-detect from environment
    """
    if not wallet_type:
        # Auto-detect from environment
        if os.getenv("LND_REST_URL"):
            wallet_type = "sovereign"
        elif os.getenv("ALBY_API_KEY"):
            wallet_type = "alby"
        elif os.getenv("LNBITS_URL"):
            wallet_type = "lnbits"
        else:
            wallet_type = "mock"

    if wallet_type == "sovereign":
        return SovereignWallet(kwargs.get("lnd_url", ""), kwargs.get("macaroon", ""))
    elif wallet_type == "alby":
        return AlbyWallet(kwargs.get("api_key", ""))
    elif wallet_type == "lnbits":
        return LNbitsWallet(kwargs.get("url", ""), kwargs.get("api_key", ""))
    else:
        return MockWallet()
