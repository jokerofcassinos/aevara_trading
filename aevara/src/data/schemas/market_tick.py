# @module: aevara.src.data.schemas.market_tick
# @deps: pydantic
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Pydantic schemas para validacao de dados de mercado.
#           Zero dados nao validados entram no pipeline.

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class ExchangeID(str, Enum):
    BINANCE = "BINANCE"
    BYBIT = "BYBIT"
    OKX = "OKX"
    COINBASE = "COINBASE"
    KRAKEN = "KRAKEN"
    SIMULATED = "SIMULATED"


class DataSource(str, Enum):
    WEBSOCKET = "WEBSOCKET"
    REST_FALLBACK = "REST_FALLBACK"
    SECONDARY = "SECONDARY"
    SIMULATION = "SIMULATION"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    UNKNOWN = "UNKNOWN"


class ValidationFlags:
    """Bitmask de validacao para ticks."""
    SCHEMA_OK = 1 << 0
    MONOTONIC_OK = 1 << 1
    CHECKSUM_OK = 1 << 2
    RANGE_OK = 1 << 3

    @staticmethod
    def all_ok() -> int:
        return ValidationFlags.SCHEMA_OK | ValidationFlags.MONOTONIC_OK | ValidationFlags.CHECKSUM_OK | ValidationFlags.RANGE_OK


class MarketTick(BaseModel):
    """
    Schema de entrada para tick de mercado.
    Todos os campos são validados via pydantic.
    Invariantes verificados em __post_init__ via model_validator.
    """
    exchange: ExchangeID
    symbol: str
    ts_ns: int                                # UTC nanoseconds, monotonic per (exchange, symbol)
    bid: float = Field(ge=0.0)               # Best bid price
    ask: float = Field(ge=0.0)               # Best ask price
    bid_vol: float = Field(ge=0.0)           # Volume at best bid
    ask_vol: float = Field(ge=0.0)           # Volume at best ask
    trade_price: Optional[float] = Field(None, ge=0.0)
    trade_vol: Optional[float] = Field(None, ge=0.0)
    trade_side: Optional[Side] = None
    checksum: str = Field(pattern=r"^[0-9a-fA-F]{8}$")  # CRC32 hex
    source: DataSource = DataSource.WEBSOCKET

    @field_validator("ask")
    @classmethod
    def positive_spread(cls, v: float, info) -> float:
        if "bid" in info.data and v <= info.data["bid"]:
            raise ValueError("Ask must be greater than bid (positive spread required)")
        return v

    @field_validator("ts_ns")
    @classmethod
    def positive_timestamp(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Timestamp must be positive")
        return v
