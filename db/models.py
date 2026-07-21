"""Pydantic v2 request/response models for Options Tycoon API."""

from typing import Literal
from pydantic import BaseModel, Field, field_validator


# --- Profile Models ---

class ProfileCreate(BaseModel):
    """Request model for creating a new trading profile."""
    name: str


class ProfileResponse(BaseModel):
    """Response model for a trading profile."""
    id: int
    name: str
    balance: float
    mode: str
    is_locked: bool
    phase: str  # 'A', 'B', 'C', 'D'
    total_trades: int


class StrategyProfileCreate(BaseModel):
    """Request model for creating a strategy sub-profile."""
    name: str


class StrategyProfileResponse(BaseModel):
    """Response model for a strategy sub-profile."""
    id: int
    profile_id: int
    name: str
    balance: float
    is_locked: bool
    created_at: str


# --- Trade Models ---

class TradeLeg(BaseModel):
    """A single leg in a multi-leg options strategy."""
    contract_type: Literal["call", "put"]
    strike: float
    expiration: str  # ISO date
    quantity: int
    action: Literal["buy", "sell"]


class TradeRequest(BaseModel):
    """Request model for executing a trade."""
    profile_id: int
    ticker: str
    strategy_type: str
    legs: list[TradeLeg]
    chain_opened_at: str  # ISO timestamp
    confirmation_proceeded: bool

    @field_validator("legs")
    @classmethod
    def validate_leg_count(cls, v: list[TradeLeg]) -> list[TradeLeg]:
        if len(v) < 1 or len(v) > 4:
            raise ValueError("Strategy must have between 1 and 4 legs")
        return v


class TradeCloseRequest(BaseModel):
    """Request model for manually closing a position."""
    outcome_tag: Literal["success", "failure", "slippage"]


# --- Market Data Models ---

class OptionsChainRow(BaseModel):
    """A single row in the options chain matrix."""
    strike: float
    call_bid: float
    call_ask: float
    call_last: float
    call_volume: int
    call_oi: int
    call_iv: float
    call_delta: float
    call_gamma: float
    call_theta: float
    call_vega: float
    put_bid: float
    put_ask: float
    put_last: float
    put_volume: int
    put_oi: int
    put_iv: float
    put_delta: float
    put_gamma: float
    put_theta: float
    put_vega: float


# --- Behavioral Models ---

class BehavioralMetrics(BaseModel):
    """Response model for behavioral profile metrics."""
    discipline_rating: float | None
    patience_score: float | None
    sizing_consistency: float | None
    emotional_reactivity: float | None
    loss_disposition_ratio: float | None
    current_streak: int
    longest_streak: int
    total_trades: int
    phase: str
    diagnostic_summary: str | None
    dna_score: int | None = None
    strategy_vs_behavior: dict | None = None
    fix_one_thing: dict | None = None
    dna_score: int | None = None
    strategy_vs_behavior: dict | None = None
    fix_one_thing: dict | None = None


# --- Journal Models ---

class JournalUpdate(BaseModel):
    """Request model for updating a trade journal note."""
    note: str = Field(max_length=1000)


# --- Real Trade Models ---

class RealTradeEntry(BaseModel):
    """Request model for logging a real trade in parallel mode."""
    ticker: str
    option_type: str
    strike_price: float
    position_size: float
    entry_time: str  # ISO timestamp
    exit_time: str  # ISO timestamp
    outcome_amount: float


# --- Error Response ---

class ErrorResponse(BaseModel):
    """Standard error response model."""
    error: bool = True
    code: str
    message: str
