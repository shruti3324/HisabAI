"""Authoritative ledger models."""

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Customer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    user_id: str = Field(default="demo", index=True)

    name: str
    normalized_name: str = Field(index=True)

    phone: Optional[str] = Field(default=None, index=True)

    preferred_reminder_language: Optional[str] = None

    reminder_enabled: bool = False
    reminder_consent: bool = False

    # demo | sms | whatsapp | voice_call
    reminder_channel: str = "demo"

    reminder_frequency_days: int = 3

    quiet_hours: Optional[str] = None

    # New collection/reminder memory
    last_reminder_at: Optional[datetime] = None
    reminder_count: int = 0

    # ISO date: YYYY-MM-DD
    promise_to_pay_date: Optional[date] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Transaction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    user_id: str = Field(default="demo", index=True)

    customer_id: Optional[int] = Field(
        default=None,
        foreign_key="customer.id",
        index=True,
    )

    customer: Optional[str] = None

    transaction_type: str = Field(
        default="sale",
        index=True,
    )

    item: Optional[str] = None
    items_json: Optional[str] = None

    total_amount: float = 0.0
    paid_amount: float = 0.0
    outstanding_amount: float = 0.0

    payment_method: Optional[str] = None

    due_date: Optional[date] = None

    payment_status: str = "unclear"

    detected_language: Optional[str] = None
    confidence: float = 0.0

    confirmed: bool = False

    raw_transcript: Optional[str] = None

    source: str = "manual"

    status: str = Field(
        default="active",
        index=True,
    )

    reversal_of: Optional[int] = Field(
        default=None,
        foreign_key="transaction.id",
    )

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        index=True,
    )

    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
    )


class AIQuery(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    user_id: str = Field(default="demo", index=True)

    query_text: str
    intent: str

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
    )


class Reminder(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    user_id: str = Field(default="demo", index=True)

    customer_id: int = Field(
        foreign_key="customer.id",
        index=True,
    )

    amount_at_reminder: float

    reminder_type: str = "payment_reminder"

    # demo | sms | whatsapp | voice_call
    channel: str = "demo"

    # scheduled | queued | sent | blocked | failed |
    # answered | promised | paid
    status: str = Field(
        default="sent",
        index=True,
    )

    message: str

    outcome: Optional[str] = None

    # Provider tracking
    provider_message_id: Optional[str] = None
    provider_call_id: Optional[str] = None

    attempt_number: int = 1

    # For future scheduled reminders
    scheduled_at: Optional[datetime] = None

    # Actual time provider call/message was sent
    sent_at: Optional[datetime] = None

    # AI decision information
    ai_decision: Optional[str] = None

    # Customer promise tracking
    promise_to_pay_date: Optional[date] = None

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        index=True,
    )


class Payment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    user_id: str = Field(default="demo", index=True)

    customer_id: int = Field(
        foreign_key="customer.id",
        index=True,
    )

    amount: float

    # demo_upi | razorpay
    provider: str = "demo_upi"

    # Internal reference / Razorpay payment link ID
    provider_reference: str = Field(index=True)

    # pending | verified | failed
    status: str = Field(
        default="pending",
        index=True,
    )

    # Razorpay payment ID
    provider_payment_id: Optional[str] = Field(
        default=None,
        index=True,
    )

    # Razorpay order ID if available
    provider_order_id: Optional[str] = Field(
        default=None,
        index=True,
    )

    payment_link_url: Optional[str] = None

    currency: str = "INR"

    # Prevent duplicate webhook reconciliation
    ledger_transaction_id: Optional[int] = Field(
        default=None,
        index=True,
    )

    verified_at: Optional[datetime] = None

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
    )