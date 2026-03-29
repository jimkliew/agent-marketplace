"""Pydantic models — all amounts in satoshis (sats)."""

import re
from pydantic import BaseModel, Field, field_validator
from backend.config import AGENT_NAME_PATTERN, MAX_TRANSACTION, MIN_TRANSACTION


# --- Agent ---

class AgentRegisterRequest(BaseModel):
    agent_name: str = Field(min_length=2, max_length=31)
    display_name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)

    @field_validator("agent_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not re.match(AGENT_NAME_PATTERN, v):
            raise ValueError("Name: 2-31 lowercase alphanumeric + hyphens, starts with letter")
        return v


class AgentRegisterResponse(BaseModel):
    agent_id: str
    agent_name: str
    token: str
    balance: int  # sats
    email: str


class AgentProfile(BaseModel):
    agent_id: str
    agent_name: str
    display_name: str
    description: str
    status: str
    reputation: float
    jobs_completed: int
    jobs_posted: int
    created_at: str


# --- Job ---

class JobCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    goals: list[str] = Field(min_length=1, max_length=10)
    tags: list[str] = Field(default_factory=list, max_length=5)
    price: int = Field(ge=MIN_TRANSACTION, le=MAX_TRANSACTION, description="Price in satoshis")

    @field_validator("goals")
    @classmethod
    def validate_goals(cls, v):
        for g in v:
            if not g or len(g) > 200:
                raise ValueError("Each goal: 1-200 chars")
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v):
        return [t.lower().strip() for t in v if t.strip()]


class JobResponse(BaseModel):
    job_id: str
    poster_id: str
    poster_name: str | None = None
    title: str
    description: str
    goals: list[str]
    tags: list[str]
    price: int  # sats
    status: str
    assigned_to: str | None
    result: str | None
    created_at: str
    updated_at: str


class JobSubmitRequest(BaseModel):
    result: str = Field(min_length=1, max_length=10000)


# --- Bid ---

class BidCreateRequest(BaseModel):
    amount: int = Field(ge=MIN_TRANSACTION, le=MAX_TRANSACTION, description="Bid amount in satoshis")
    message: str = Field(default="", max_length=500)


class BidResponse(BaseModel):
    bid_id: str
    job_id: str
    bidder_id: str
    bidder_name: str | None = None
    amount: int  # sats
    message: str
    status: str
    created_at: str


# --- Message ---

class MessageSendRequest(BaseModel):
    to_agent_name: str = Field(min_length=2, max_length=31)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)
    thread_id: str | None = None


class MessageResponse(BaseModel):
    message_id: str
    from_agent_id: str
    from_agent_name: str | None = None
    to_agent_id: str
    to_agent_name: str | None = None
    subject: str
    body: str
    is_read: bool
    thread_id: str | None
    created_at: str


# --- Escrow ---

class DepositRequest(BaseModel):
    amount: int = Field(ge=1, le=MAX_TRANSACTION, description="Deposit amount in satoshis")


class LedgerEntry(BaseModel):
    tx_id: str
    from_agent_id: str | None
    to_agent_id: str | None
    amount: int  # sats
    currency: str
    unit: str
    tx_type: str
    reference_id: str | None
    description: str
    created_at: str


# --- Platform ---

class PlatformStats(BaseModel):
    total_agents: int
    active_agents: int
    total_jobs: int
    open_jobs: int
    completed_jobs: int
    total_escrow_held: int  # sats
    total_volume: int  # sats
    total_messages: int
    total_events: int
    currency: str
    unit: str
