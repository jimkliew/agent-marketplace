"""Configuration — all constants and env vars loaded at import time."""

import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.getenv("DB_PATH", "data/agent_market.db")
DB_FULL_PATH = BASE_DIR / DB_PATH

# Security
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", secrets.token_hex(32))

# Server
API_PORT = int(os.getenv("API_PORT", "8000"))
API_HOST = os.getenv("API_HOST", "0.0.0.0")

# --- Multi-Currency Payment System ---
# Supported currencies and their atomic units:
#   BTC  → satoshis (sats)    1 BTC = 100,000,000 sats
#   ETH  → gwei               1 ETH = 1,000,000,000 gwei
#   ADA  → lovelace           1 ADA = 1,000,000 lovelace
#   USDT → cents              1 USDT = 100 cents
#   USDC → cents              1 USDC = 100 cents
PAYMENT_CURRENCY = os.getenv("PAYMENT_CURRENCY", "BTC")
PAYMENT_UNIT = os.getenv("PAYMENT_UNIT", "sats")

# All amounts stored as integers in the atomic unit
MIN_DEPOSIT = int(os.getenv("MIN_DEPOSIT", "1000"))       # 1,000 sats default
MAX_TRANSACTION = int(os.getenv("MAX_TRANSACTION", "100000"))  # 100,000 sats default
MIN_TRANSACTION = 1  # 1 sat minimum

# Currency display config
CURRENCY_SYMBOLS = {
    "BTC": {"unit": "sats", "symbol": "₿", "decimals": 8, "atoms_per_unit": 100_000_000},
    "ETH": {"unit": "gwei", "symbol": "Ξ", "decimals": 9, "atoms_per_unit": 1_000_000_000},
    "ADA": {"unit": "lovelace", "symbol": "₳", "decimals": 6, "atoms_per_unit": 1_000_000},
    "USDT": {"unit": "cents", "symbol": "$", "decimals": 2, "atoms_per_unit": 100},
    "USDC": {"unit": "cents", "symbol": "$", "decimals": 2, "atoms_per_unit": 100},
}

CURRENCY_CONFIG = CURRENCY_SYMBOLS.get(PAYMENT_CURRENCY, CURRENCY_SYMBOLS["BTC"])

# Platform fees (revenue)
PLATFORM_FEE_BPS = int(os.getenv("PLATFORM_FEE_BPS", "600"))  # 600 = 6.00%
# Fee is deducted from escrow release: worker gets (amount - fee), platform keeps fee
# Set to 0 for no fee. Max 1000 (10%).

# Agent name rules
AGENT_NAME_PATTERN = r"^[a-z][a-z0-9-]{1,30}$"

# Rate limits (requests, window_seconds)
RATE_LIMIT_REGISTER = (5, 3600)
RATE_LIMIT_JOB_POST = (10, 60)
RATE_LIMIT_BID = (20, 60)
RATE_LIMIT_MESSAGE = (30, 60)
RATE_LIMIT_DEFAULT = (60, 60)

# Text field limits
MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 2000
MAX_MESSAGE_BODY_LENGTH = 5000
MAX_GOALS_COUNT = 10
MAX_GOAL_LENGTH = 200
MAX_BID_MESSAGE_LENGTH = 500

# Pagination
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def format_amount(atomic_units: int) -> str:
    """Format atomic units for display. e.g., 1500 sats → '1,500 sats'"""
    return f"{atomic_units:,} {PAYMENT_UNIT}"


def validate_config():
    """Validate configuration at startup."""
    DB_FULL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if PAYMENT_CURRENCY not in CURRENCY_SYMBOLS:
        raise ValueError(f"Unsupported currency: {PAYMENT_CURRENCY}. Use: {list(CURRENCY_SYMBOLS.keys())}")
    if SECRET_KEY == "change-me-to-a-random-64-char-hex-string":
        print("WARNING: Using default SECRET_KEY. Set SECRET_KEY in .env for production.")
    if ADMIN_TOKEN == "change-me-to-a-random-admin-token":
        print("WARNING: Using default ADMIN_TOKEN. Set ADMIN_TOKEN in .env for production.")
    print(f"Payment: {PAYMENT_CURRENCY} ({PAYMENT_UNIT}), min deposit: {format_amount(MIN_DEPOSIT)}, max tx: {format_amount(MAX_TRANSACTION)}")
