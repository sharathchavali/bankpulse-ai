"""
Pydantic schemas for every record type flowing through the pipeline.

These are the *contract* between the synthetic data generator, the ingestion
layer, and the downstream Spark / SQL layers. Every row is validated before
it's written, which catches schema drift early and gives us free JSON-schema
generation for the data catalog later.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------- Enums -----------------------------------------------------------


class CardNetwork(StrEnum):
    VISA = "VISA"
    MASTERCARD = "MASTERCARD"
    AMEX = "AMEX"


class Channel(StrEnum):
    CARD_PRESENT = "CARD_PRESENT"
    ECOMMERCE = "ECOMMERCE"
    CONTACTLESS = "CONTACTLESS"
    ATM = "ATM"
    TRANSFER = "TRANSFER"


class TransactionStatus(StrEnum):
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    PENDING = "PENDING"
    REVERSED = "REVERSED"


class FraudPattern(StrEnum):
    """Ground-truth label. NONE = legitimate."""
    NONE = "NONE"
    CARD_TESTING = "CARD_TESTING"
    ACCOUNT_TAKEOVER = "ACCOUNT_TAKEOVER"
    SYNTHETIC_IDENTITY = "SYNTHETIC_IDENTITY"
    VELOCITY_ATTACK = "VELOCITY_ATTACK"
    IMPOSSIBLE_TRAVEL = "IMPOSSIBLE_TRAVEL"
    MERCHANT_COLLUSION = "MERCHANT_COLLUSION"


# ---------- Base config -----------------------------------------------------


class _Base(BaseModel):
    """Shared strict config for all models."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
        frozen=False,
    )


# ---------- Dimensions ------------------------------------------------------


class Customer(_Base):
    customer_id: UUID
    first_name: str
    last_name: str
    email: str
    date_of_birth: date
    home_city: str
    home_country: str = Field(min_length=2, max_length=2)  # ISO-3166 alpha-2
    signup_date: date
    risk_segment: Annotated[str, Field(pattern="^(LOW|MEDIUM|HIGH)$")]
    annual_income_eur: Decimal = Field(ge=0)

    @field_validator("home_country")
    @classmethod
    def upper_country(cls, v: str) -> str:
        return v.upper()


class Merchant(_Base):
    merchant_id: UUID
    merchant_name: str
    mcc: int = Field(ge=1000, le=9999)          # Merchant Category Code
    mcc_description: str
    city: str
    country: str = Field(min_length=2, max_length=2)
    is_online: bool
    risk_flag: bool = False                     # Known-shady merchants


class Card(_Base):
    card_id: UUID
    customer_id: UUID
    card_network: CardNetwork
    issued_date: date
    expiry_date: date
    is_active: bool = True


# ---------- Fact ------------------------------------------------------------


class Transaction(_Base):
    transaction_id: UUID
    customer_id: UUID
    card_id: UUID
    merchant_id: UUID
    transaction_ts: datetime
    amount_eur: Decimal = Field(gt=0, decimal_places=2)
    channel: Channel
    status: TransactionStatus
    # Geo captured at event time (device/IP lookup in real systems)
    location_city: str
    location_country: str = Field(min_length=2, max_length=2)
    # Ground-truth fraud label — never exposed to the model, only used for eval
    is_fraud: bool = False
    fraud_pattern: FraudPattern = FraudPattern.NONE

    @field_validator("location_country")
    @classmethod
    def upper_country(cls, v: str) -> str:
        return v.upper()