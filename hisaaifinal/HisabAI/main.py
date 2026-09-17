from __future__ import annotations

import asyncio
import os
import tempfile
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import select
from nicegui import ui

from db import get_session, init_db
from models import Customer, Transaction, Reminder

from services import ai_service

from services.reminder_service import (
    send_reminder,
    schedule_reminder,
    execute_scheduled_reminder,
    build_voice_twiml,
    process_voice_response,
    update_voice_status,
    list_reminder_history,
    update_reminder_settings,
    reminder_candidates,
)


# ============================================================
# ENVIRONMENT
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")

load_dotenv(ENV_FILE, override=True)

print("=" * 60)
print("HISABAI — VOICE LEDGER")
print("=" * 60)
print("[ENV] .env:", ENV_FILE)
print("[ENV] .env exists:", os.path.exists(ENV_FILE))
print("[ENV] GROQ_API_KEY:", bool(os.getenv("GROQ_API_KEY")))
print("[ENV] TWILIO_ACCOUNT_SID:", bool(os.getenv("TWILIO_ACCOUNT_SID")))
print("[ENV] TWILIO_AUTH_TOKEN:", bool(os.getenv("TWILIO_AUTH_TOKEN")))
print("[ENV] TWILIO_PHONE_NUMBER:", bool(os.getenv("TWILIO_PHONE_NUMBER")))
print("[ENV] PUBLIC_BASE_URL:", bool(os.getenv("PUBLIC_BASE_URL")))
print("=" * 60)


# ============================================================
# CONFIG
# ============================================================

HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "8080"))
USER_ID = "demo"


# ============================================================
# SCHEDULER
# ============================================================

_scheduler_task = None
_scheduler_running = False
SCHEDULER_INTERVAL = 15


async def reminder_scheduler_loop():
    global _scheduler_running

    print("[SCHEDULER] Scheduled reminder engine is running.")

    while _scheduler_running:
        try:
            now = datetime.utcnow()

            with get_session() as session:
                reminders = session.exec(
                    select(Reminder)
                    .where(
                        Reminder.status == "scheduled",
                        Reminder.scheduled_at <= now,
                    )
                ).all()

            for reminder in reminders:
                try:
                    print(
                        f"[SCHEDULER] Executing reminder #{reminder.id}"
                    )

                    await asyncio.to_thread(
                        execute_scheduled_reminder,
                        reminder.id,
                    )

                except Exception as exc:
                    print(
                        f"[SCHEDULER] Reminder #{reminder.id} failed:",
                        repr(exc),
                    )

        except Exception as exc:
            print(
                "[SCHEDULER] Loop error:",
                repr(exc),
            )

        await asyncio.sleep(SCHEDULER_INTERVAL)


def start_scheduler():
    global _scheduler_task
    global _scheduler_running

    if _scheduler_task is not None:
        return

    print("[SCHEDULER] Starting scheduler...")

    _scheduler_running = True

    try:
        loop = asyncio.get_running_loop()

        _scheduler_task = loop.create_task(
            reminder_scheduler_loop()
        )

        print("[SCHEDULER] Background scheduler started.")

    except RuntimeError as exc:
        print(
            "[SCHEDULER] Could not start:",
            repr(exc),
        )


def stop_scheduler():
    global _scheduler_task
    global _scheduler_running

    _scheduler_running = False

    if _scheduler_task:
        _scheduler_task.cancel()
        _scheduler_task = None

    print("[SCHEDULER] Scheduler stopped.")


# ============================================================
# HELPERS
# ============================================================

def dump(value: Any) -> Any:

    if hasattr(value, "model_dump"):
        return value.model_dump()

    if hasattr(value, "dict"):
        return value.dict()

    if isinstance(value, list):
        return [dump(item) for item in value]

    if isinstance(value, dict):
        return {
            key: dump(item)
            for key, item in value.items()
        }

    return value


def money(value: Any) -> float:

    try:
        return round(float(value or 0), 2)
    except Exception:
        return 0.0


def normalize_name(name: str | None) -> str:

    if not name:
        return ""

    return " ".join(
        name.strip().lower().split()
    )


def normalize_phone(phone: str | None) -> str | None:

    if not phone:
        return None

    phone = str(phone).strip()

    if not phone:
        return None

    # Keep +91XXXXXXXXXX
    if phone.startswith("+"):
        digits = "+" + "".join(
            c for c in phone[1:]
            if c.isdigit()
        )

        if len(digits) >= 10:
            return digits

    # Remove spaces, -, brackets, etc.
    digits = "".join(
        c for c in phone
        if c.isdigit()
    )

    # Indian 10 digit number
    if len(digits) == 10 and digits[0] in "6789":
        return "+91" + digits

    # 91XXXXXXXXXX
    if len(digits) == 12 and digits.startswith("91"):
        return "+" + digits

    # Return cleaned number if it doesn't match
    # standard Indian format.
    return digits or None


def transaction_to_dict(
    transaction: Transaction,
) -> dict:

    return {
        "id": transaction.id,
        "customer_id": transaction.customer_id,
        "customer": transaction.customer,
        "transaction_type": transaction.transaction_type,
        "item": transaction.item,
        "items_json": transaction.items_json,
        "total_amount": money(transaction.total_amount),
        "paid_amount": money(transaction.paid_amount),
        "outstanding_amount": money(
            transaction.outstanding_amount
        ),
        "payment_method": transaction.payment_method,
        "due_date": (
            transaction.due_date.isoformat()
            if transaction.due_date
            else None
        ),
        "payment_status": transaction.payment_status,
        "detected_language": transaction.detected_language,
        "confidence": transaction.confidence,
        "confirmed": transaction.confirmed,
        "raw_transcript": transaction.raw_transcript,
        "source": transaction.source,
        "status": transaction.status,
        "created_at": (
            transaction.created_at.isoformat()
            if transaction.created_at
            else None
        ),
    }


def customer_outstanding(
    customer_id: int,
    user_id: str = USER_ID,
) -> float:

    with get_session() as session:

        transactions = session.exec(
            select(Transaction)
            .where(
                Transaction.user_id == user_id,
                Transaction.customer_id == customer_id,
                Transaction.status == "active",
            )
        ).all()

        total = sum(
            money(t.outstanding_amount)
            for t in transactions
        )

        return round(max(total, 0), 2)


def customer_to_dict(
    customer: Customer,
    user_id: str = USER_ID,
) -> dict:

    outstanding = customer_outstanding(
        customer.id,
        user_id,
    )

    return {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "preferred_reminder_language":
            customer.preferred_reminder_language,
        "reminder_enabled":
            customer.reminder_enabled,
        "reminder_consent":
            customer.reminder_consent,
        "reminder_channel":
            customer.reminder_channel,
        "reminder_frequency_days":
            customer.reminder_frequency_days,
        "quiet_hours":
            customer.quiet_hours,
        "promise_to_pay_date": (
            customer.promise_to_pay_date.isoformat()
            if customer.promise_to_pay_date
            else None
        ),
        "last_reminder_at": (
            customer.last_reminder_at.isoformat()
            if customer.last_reminder_at
            else None
        ),
        "reminder_count":
            customer.reminder_count,
        "outstanding_amount":
            outstanding,
        "created_at": (
            customer.created_at.isoformat()
            if customer.created_at
            else None
        ),
    }


def reminder_to_dict(
    reminder: Reminder,
) -> dict:

    return {
        "id": reminder.id,
        "customer_id": reminder.customer_id,
        "amount_at_reminder":
            money(reminder.amount_at_reminder),
        "reminder_type": reminder.reminder_type,
        "channel": reminder.channel,
        "status": reminder.status,
        "message": reminder.message,
        "outcome": reminder.outcome,
        "provider_message_id":
            reminder.provider_message_id,
        "provider_call_id":
            reminder.provider_call_id,
        "attempt_number":
            reminder.attempt_number,
        "scheduled_at": (
            reminder.scheduled_at.isoformat()
            if reminder.scheduled_at
            else None
        ),
        "sent_at": (
            reminder.sent_at.isoformat()
            if reminder.sent_at
            else None
        ),
        "ai_decision":
            reminder.ai_decision,
        "promise_to_pay_date": (
            reminder.promise_to_pay_date.isoformat()
            if reminder.promise_to_pay_date
            else None
        ),
        "created_at": (
            reminder.created_at.isoformat()
            if reminder.created_at
            else None
        ),
    }


# ============================================================
# CUSTOMER HELPERS
# ============================================================

def get_or_create_customer(
    session,
    name: str,
    user_id: str = USER_ID,
    phone: str | None = None,
) -> Customer:

    normalized = normalize_name(name)
    phone = normalize_phone(phone)

    customer = session.exec(
        select(Customer)
        .where(
            Customer.user_id == user_id,
            Customer.normalized_name == normalized,
        )
    ).first()

    if customer:

        if phone and phone != customer.phone:
            customer.phone = phone
            customer.updated_at = datetime.utcnow()

            session.add(customer)
            session.commit()
            session.refresh(customer)

        return customer

    customer = Customer(
        user_id=user_id,
        name=name.strip(),
        normalized_name=normalized,
        phone=phone,
        reminder_enabled=False,
        reminder_consent=False,
        reminder_channel="voice_call",
        reminder_frequency_days=3,
    )

    session.add(customer)
    session.commit()
    session.refresh(customer)

    return customer


# ============================================================
# LIFESPAN
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    print()
    print("=" * 60)
    print("VOICE LEDGER STARTING")
    print("=" * 60)

    init_db()
    start_scheduler()

    try:
        yield

    finally:
        stop_scheduler()


# ============================================================
# FASTAPI
# ============================================================

fastapi_app = FastAPI(
    title="HisabAI — Voice Ledger",
    version="1.0.0",
    lifespan=lifespan,
)

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# HEALTH
# ============================================================

@fastapi_app.get("/api/health")
async def health():

    return {
        "success": True,
        "status": "healthy",
        "app": "HisabAI",
        "groq_configured":
            bool(os.getenv("GROQ_API_KEY")),
        "twilio_configured": all([
            os.getenv("TWILIO_ACCOUNT_SID"),
            os.getenv("TWILIO_AUTH_TOKEN"),
            os.getenv("TWILIO_PHONE_NUMBER"),
            os.getenv("PUBLIC_BASE_URL"),
        ]),
    }


# ============================================================
# DASHBOARD
# ============================================================

@fastapi_app.get("/api/dashboard")
async def dashboard():

    with get_session() as session:

        transactions = session.exec(
            select(Transaction)
            .where(
                Transaction.user_id == USER_ID,
                Transaction.status == "active",
            )
        ).all()

        customers = session.exec(
            select(Customer)
            .where(
                Customer.user_id == USER_ID
            )
        ).all()

    total_sales = sum(
        money(t.total_amount)
        for t in transactions
        if t.transaction_type == "sale"
    )

    received = sum(
        money(t.paid_amount)
        for t in transactions
    )

    outstanding = sum(
        money(t.outstanding_amount)
        for t in transactions
    )

    today = date.today()

    today_sales = sum(
        money(t.total_amount)
        for t in transactions
        if (
            t.created_at
            and t.created_at.date() == today
            and t.transaction_type == "sale"
        )
    )

    recent_transactions = sorted(
        transactions,
        key=lambda t: t.created_at or datetime.min,
        reverse=True,
    )[:10]

    recent_customers = sorted(
        customers,
        key=lambda c: c.created_at or datetime.min,
        reverse=True,
    )[:10]

    return {
        "success": True,
        "metrics": {
            "today_sales": today_sales,
            "total_sales": total_sales,
            "received": received,
            "outstanding": outstanding,
            "customers": len(customers),
        },
        "recent_transactions": [
            transaction_to_dict(t)
            for t in recent_transactions
        ],
        "recent_customers": [
            customer_to_dict(c)
            for c in recent_customers
        ],
    }


# ============================================================
# TRANSACTIONS
# ============================================================

@fastapi_app.get("/api/transactions")
async def transactions():

    with get_session() as session:

        rows = session.exec(
            select(Transaction)
            .where(
                Transaction.user_id == USER_ID
            )
            .order_by(
                Transaction.created_at.desc()
            )
        ).all()

        return {
            "success": True,
            "transactions": [
                transaction_to_dict(t)
                for t in rows
            ],
        }


class ConfirmTransactionRequest(BaseModel):

    customer: str
    phone: Optional[str] = None
    item: Optional[str] = None
    transaction_type: str = "sale"
    total_amount: float = 0
    paid_amount: float = 0
    payment_method: Optional[str] = None
    due_date: Optional[date] = None
    payment_status: Optional[str] = None
    detected_language: Optional[str] = None
    confidence: float = 0
    raw_transcript: Optional[str] = None


@fastapi_app.post("/api/transactions/confirm")
async def confirm_transaction(
    payload: ConfirmTransactionRequest,
):

    total = max(
        money(payload.total_amount),
        0,
    )

    paid = max(
        money(payload.paid_amount),
        0,
    )

    if paid > total:
        paid = total

    outstanding = round(
        max(total - paid, 0),
        2,
    )

    if outstanding <= 0:
        status = "paid"
    elif paid > 0:
        status = "partial"
    else:
        status = "pending"

    if payload.payment_status:
        status = payload.payment_status

    with get_session() as session:

        customer = get_or_create_customer(
            session=session,
            name=payload.customer,
            user_id=USER_ID,
            phone=payload.phone,
        )

        transaction = Transaction(
            user_id=USER_ID,
            customer_id=customer.id,
            customer=customer.name,
            transaction_type=(
                payload.transaction_type or "sale"
            ),
            item=payload.item,
            total_amount=total,
            paid_amount=paid,
            outstanding_amount=outstanding,
            payment_method=payload.payment_method,
            due_date=payload.due_date,
            payment_status=status,
            detected_language=(
                payload.detected_language
            ),
            confidence=payload.confidence,
            confirmed=True,
            raw_transcript=(
                payload.raw_transcript
            ),
            source="voice",
            status="active",
        )

        session.add(transaction)
        session.commit()
        session.refresh(transaction)

        return {
            "success": True,
            "message":
                "Transaction saved successfully.",
            "transaction":
                transaction_to_dict(transaction),
            "customer":
                customer_to_dict(customer),
        }


@fastapi_app.post(
    "/api/transactions/{transaction_id}/reverse"
)
async def reverse_transaction(
    transaction_id: int,
):

    with get_session() as session:

        transaction = session.get(
            Transaction,
            transaction_id,
        )

        if (
            not transaction
            or transaction.user_id != USER_ID
        ):
            raise HTTPException(
                status_code=404,
                detail="Transaction not found.",
            )

        transaction.status = "reversed"
        transaction.updated_at = datetime.utcnow()

        session.add(transaction)
        session.commit()

        return {
            "success": True,
            "message": "Transaction reversed.",
        }


# ============================================================
# CUSTOMERS
# ============================================================

class CustomerCreateRequest(BaseModel):

    name: str
    phone: Optional[str] = None
    preferred_reminder_language: Optional[str] = "hindi"
    reminder_enabled: bool = False
    reminder_consent: bool = False


class CustomerUpdateRequest(BaseModel):

    name: Optional[str] = None
    phone: Optional[str] = None
    preferred_reminder_language: Optional[str] = None
    reminder_enabled: Optional[bool] = None
    reminder_consent: Optional[bool] = None
    reminder_frequency_days: Optional[int] = None
    quiet_hours: Optional[str] = None


@fastapi_app.get("/api/customers")
async def customers():

    with get_session() as session:

        rows = session.exec(
            select(Customer)
            .where(
                Customer.user_id == USER_ID
            )
            .order_by(
                Customer.created_at.desc()
            )
        ).all()

        return {
            "success": True,
            "customers": [
                customer_to_dict(c)
                for c in rows
            ],
        }


@fastapi_app.post("/api/customers")
async def create_customer(
    payload: CustomerCreateRequest,
):

    name = payload.name.strip()

    if not name:
        return {
            "success": False,
            "error": "Customer name is required.",
        }

    phone = normalize_phone(payload.phone)

    with get_session() as session:

        existing = session.exec(
            select(Customer)
            .where(
                Customer.user_id == USER_ID,
                Customer.normalized_name ==
                normalize_name(name),
            )
        ).first()

        if existing:

            if phone:
                existing.phone = phone

            existing.reminder_enabled = (
                payload.reminder_enabled
            )

            existing.reminder_consent = (
                payload.reminder_consent
            )

            existing.preferred_reminder_language = (
                payload.preferred_reminder_language
            )

            existing.updated_at = datetime.utcnow()

            session.add(existing)
            session.commit()
            session.refresh(existing)

            return {
                "success": True,
                "message":
                    "Customer already existed. Details updated.",
                "customer":
                    customer_to_dict(existing),
            }

        customer = Customer(
            user_id=USER_ID,
            name=name,
            normalized_name=normalize_name(name),
            phone=phone,
            preferred_reminder_language=(
                payload.preferred_reminder_language
            ),
            reminder_enabled=(
                payload.reminder_enabled
            ),
            reminder_consent=(
                payload.reminder_consent
            ),
            reminder_channel="voice_call",
            reminder_frequency_days=3,
        )

        session.add(customer)
        session.commit()
        session.refresh(customer)

        return {
            "success": True,
            "message": "Customer created.",
            "customer":
                customer_to_dict(customer),
        }


@fastapi_app.put(
    "/api/customers/{customer_id}"
)
async def update_customer(
    customer_id: int,
    payload: CustomerUpdateRequest,
):

    with get_session() as session:

        customer = session.get(
            Customer,
            customer_id,
        )

        if (
            not customer
            or customer.user_id != USER_ID
        ):
            raise HTTPException(
                status_code=404,
                detail="Customer not found.",
            )

        if payload.name is not None:
            name = payload.name.strip()

            if name:
                customer.name = name
                customer.normalized_name = (
                    normalize_name(name)
                )

        if payload.phone is not None:
            customer.phone = normalize_phone(
                payload.phone
            )

        if payload.preferred_reminder_language is not None:
            customer.preferred_reminder_language = (
                payload.preferred_reminder_language
            )

        if payload.reminder_enabled is not None:
            customer.reminder_enabled = (
                payload.reminder_enabled
            )

        if payload.reminder_consent is not None:
            customer.reminder_consent = (
                payload.reminder_consent
            )

        if payload.reminder_frequency_days is not None:
            customer.reminder_frequency_days = max(
                1,
                int(payload.reminder_frequency_days),
            )

        if payload.quiet_hours is not None:
            customer.quiet_hours = (
                payload.quiet_hours
            )

        customer.updated_at = datetime.utcnow()

        session.add(customer)
        session.commit()
        session.refresh(customer)

        return {
            "success": True,
            "message": "Customer updated.",
            "customer":
                customer_to_dict(customer),
        }


@fastapi_app.get(
    "/api/customers/{customer_id}"
)
async def get_customer(
    customer_id: int,
):

    with get_session() as session:

        customer = session.get(
            Customer,
            customer_id,
        )

        if (
            not customer
            or customer.user_id != USER_ID
        ):
            raise HTTPException(
                status_code=404,
                detail="Customer not found.",
            )

        transactions = session.exec(
            select(Transaction)
            .where(
                Transaction.user_id == USER_ID,
                Transaction.customer_id == customer_id,
                Transaction.status == "active",
            )
            .order_by(
                Transaction.created_at.desc()
            )
        ).all()

        return {
            "success": True,
            "customer":
                customer_to_dict(customer),
            "transactions": [
                transaction_to_dict(t)
                for t in transactions
            ],
        }


# ============================================================
# REMINDER CANDIDATES
# ============================================================

@fastapi_app.get(
    "/api/reminder-candidates"
)
async def get_reminder_candidates():

    try:

        candidates = reminder_candidates(
            USER_ID
        )

        return {
            "success": True,
            "candidates": candidates,
        }

    except Exception as exc:

        print(
            "[REMINDER CANDIDATES ERROR]",
            repr(exc),
        )

        return {
            "success": False,
            "error": str(exc),
            "candidates": [],
        }


# ============================================================
# REMINDER SETTINGS
# ============================================================

@fastapi_app.post(
    "/api/customers/{customer_id}/reminder-settings"
)
async def save_reminder_settings(
    customer_id: int,
    payload: dict,
):

    try:

        customer = update_reminder_settings(
            customer_id=customer_id,
            payload=payload,
            user_id=USER_ID,
        )

        return {
            "success": True,
            "message":
                "Reminder settings saved.",
            "customer":
                customer_to_dict(customer),
        }

    except ValueError as exc:

        return {
            "success": False,
            "error": str(exc),
        }

    except Exception as exc:

        print(
            "[REMINDER SETTINGS ERROR]",
            repr(exc),
        )

        return {
            "success": False,
            "error": str(exc),
        }


# ============================================================
# SEND REMINDER
# ============================================================

@fastapi_app.post(
    "/api/customers/{customer_id}/reminder"
)
async def create_reminder(
    customer_id: int,
    payload: Optional[dict] = None,
):

    payload = payload or {}

    try:

        print(
            f"[REMINDER] Request received for customer #{customer_id}"
        )

        # Check customer and allow an explicit UI action to enable
        # reminders + consent before attempting the call.
        if payload.get("enable_reminders") is True:
            with get_session() as session:
                customer = session.get(Customer, customer_id)

                if not customer or customer.user_id != USER_ID:
                    raise HTTPException(
                        status_code=404,
                        detail="Customer not found.",
                    )

                customer.reminder_enabled = True
                customer.reminder_consent = True
                customer.reminder_channel = "voice_call"
                customer.updated_at = datetime.utcnow()

                session.add(customer)
                session.commit()

                print(
                    f"[REMINDER] Reminders enabled for customer #{customer_id}"
                )

        force = bool(
            payload.get("force", False)
        )

        result = send_reminder(
            customer_id=customer_id,
            user_id=USER_ID,
            force=force,
        )

        return {
            "success": True,
            "message":
                "Reminder sent successfully.",
            "reminder":
                reminder_to_dict(result),
        }

    except ValueError as exc:

        error_text = str(exc)

        print(
            "[REMINDER] Validation error:",
            error_text,
        )

        if "disabled" in error_text.lower():
            return {
                "success": False,
                "error_type": "REMINDERS_DISABLED",
                "reminders_disabled": True,
                "error": error_text,
                "message": "Reminders are disabled for this customer.",
                "user_message": "Enable reminders and customer consent first.",
                "customer_id": customer_id,
            }

        return {
            "success": False,
            "error_type": "VALIDATION_ERROR",
            "error": error_text,
            "message": error_text,
            "customer_id": customer_id,
        }

    except Exception as exc:

        error_text = str(exc)
        lower_error = error_text.lower()

        print(
            "[REMINDER] Provider/application error:",
            repr(exc),
        )

        twilio_trial_error = any(
            phrase in lower_error
            for phrase in [
                "trial accounts have limited parameter access",
                "upgrade your account to unlock full functionality",
                "unable to create record",
                "/calls.json",
                "twilio",
            ]
        )

        if twilio_trial_error:
            return {
                "success": False,
                "provider_error": True,
                "error_type": "TWILIO_TRIAL_RESTRICTION",
                "message": (
                    "Reminder was processed, but Twilio could not place "
                    "the voice call because the Twilio account is still on trial."
                ),
                "user_message": (
                    "📞 Reminder processed. Twilio could not place the voice call "
                    "because the account is still on a trial plan."
                ),
                "customer_id": customer_id,
            }

        return {
            "success": False,
            "provider_error": True,
            "error_type": "REMINDER_PROVIDER_ERROR",
            "error": "The reminder could not be sent.",
            "message": "The reminder could not be sent.",
            "user_message": "The reminder could not be sent right now. Please try again.",
            "customer_id": customer_id,
        }


# ============================================================
# SCHEDULE REMINDER
# ============================================================

class ScheduleReminderRequest(BaseModel):
    scheduled_at: datetime


@fastapi_app.post(
    "/api/customers/{customer_id}/reminders"
)
async def schedule_customer_reminder(
    customer_id: int,
    payload: ScheduleReminderRequest,
):

    try:

        reminder = schedule_reminder(
            customer_id=customer_id,
            scheduled_at=payload.scheduled_at,
            user_id=USER_ID,
        )

        return {
            "success": True,
            "message":
                "Reminder scheduled successfully.",
            "reminder":
                reminder_to_dict(reminder),
        }

    except Exception as exc:

        print(
            "[REMINDER SCHEDULE ERROR]",
            repr(exc),
        )

        return {
            "success": False,
            "error": str(exc),
        }


# ============================================================
# REMINDER HISTORY
# ============================================================

@fastapi_app.get(
    "/api/customers/{customer_id}/reminders"
)
async def customer_reminders(
    customer_id: int,
):

    try:

        rows = list_reminder_history(
            customer_id=customer_id,
            user_id=USER_ID,
        )

        return {
            "success": True,
            "reminders": [
                reminder_to_dict(r)
                for r in rows
            ],
        }

    except Exception as exc:

        print(
            "[REMINDER HISTORY ERROR]",
            repr(exc),
        )

        return {
            "success": False,
            "error": str(exc),
            "reminders": [],
        }


# ============================================================
# TWILIO VOICE WEBHOOK
# ============================================================

@fastapi_app.post(
    "/api/reminders/voice/{reminder_id}"
)
async def reminder_voice(
    reminder_id: int,
):

    with get_session() as session:

        reminder = session.get(
            Reminder,
            reminder_id,
        )

        if not reminder:

            return Response(
                content="""<?xml version="1.0" encoding="UTF-8"?>
<Response>
<Say>Reminder not found.</Say>
</Response>""",
                media_type="application/xml",
            )

        try:

            twiml = build_voice_twiml(
                reminder
            )

            return Response(
                content=twiml,
                media_type="application/xml",
            )

        except Exception as exc:

            print(
                "[TWILIO VOICE ERROR]",
                repr(exc),
            )

            return Response(
                content="""<?xml version="1.0" encoding="UTF-8"?>
<Response>
<Say>Sorry, an error occurred.</Say>
</Response>""",
                media_type="application/xml",
            )


# ============================================================
# TWILIO VOICE RESPONSE
# ============================================================

@fastapi_app.post(
    "/api/reminders/voice-response/{reminder_id}"
)
async def reminder_voice_response(
    reminder_id: int,
    SpeechResult: Optional[str] = Form(None),
):

    try:

        reminder = process_voice_response(
            reminder_id=reminder_id,
            speech_result=SpeechResult,
        )

        message = (
            "Dhanyavaad. Aapka response record kar liya gaya."
        )

        if reminder.status == "promised":

            message = (
                "Dhanyavaad. Aapka payment promise record kar liya gaya."
            )

        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
<Say language="hi-IN" voice="alice">
{message}
</Say>
</Response>
"""

        return Response(
            content=twiml,
            media_type="application/xml",
        )

    except Exception as exc:

        print(
            "[TWILIO RESPONSE ERROR]",
            repr(exc),
        )

        return Response(
            content="""<?xml version="1.0" encoding="UTF-8"?>
<Response>
<Say language="hi-IN" voice="alice">
Dhanyavaad. Aapka din shubh ho.
</Say>
</Response>
""",
            media_type="application/xml",
        )


# ============================================================
# TWILIO STATUS CALLBACK
# ============================================================

@fastapi_app.post(
    "/api/reminders/voice-status"
)
async def reminder_voice_status(
    CallSid: Optional[str] = Form(None),
    CallStatus: Optional[str] = Form(None),
):

    try:

        if not CallSid:
            return {
                "success": False,
                "error": "CallSid is missing.",
            }

        if not CallStatus:
            return {
                "success": False,
                "error": "CallStatus is missing.",
            }

        reminder = update_voice_status(
            call_sid=CallSid,
            call_status=CallStatus,
        )

        return {
            "success": True,
            "found": reminder is not None,
            "status": (
                reminder.status
                if reminder
                else None
            ),
        }

    except Exception as exc:

        print(
            "[TWILIO STATUS ERROR]",
            repr(exc),
        )

        return {
            "success": False,
            "error": str(exc),
        }


# ============================================================
# VOICE NOTE PROCESSING
# ============================================================

@fastapi_app.post(
    "/api/process_voice_note"
)
async def process_voice_note(
    file: UploadFile = File(...),
):

    temp_path = None

    try:

        suffix = ".webm"

        if file.filename:

            extension = os.path.splitext(
                file.filename
            )[1]

            if extension:
                suffix = extension

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=suffix,
        ) as temp:

            temp_path = temp.name

            while True:

                chunk = await file.read(
                    1024 * 1024
                )

                if not chunk:
                    break

                temp.write(chunk)

        print(
            f"[VOICE] Received audio: {file.filename}"
        )

        result = ai_service.process_voice_note(
            temp_path
        )

        return {
            "success": True,
            **dump(result),
        }

    except Exception as exc:

        print(
            "[VOICE ERROR]",
            repr(exc),
        )

        return {
            "success": False,
            "error": str(exc),
        }

    finally:

        if (
            temp_path
            and os.path.exists(temp_path)
        ):

            try:
                os.remove(temp_path)
            except Exception:
                pass


# ============================================================
# BUSINESS QUERY
# ============================================================

class BusinessQueryRequest(BaseModel):
    query: str


@fastapi_app.post(
    "/api/business-query"
)
async def business_query(
    payload: BusinessQueryRequest,
):

    query = payload.query.strip()

    if not query:
        return {
            "success": False,
            "error": "Query is empty.",
        }

    return {
        "success": True,
        "query": query,
        "message": "Business query received.",
    }


# ============================================================
# CSS
# ============================================================

APP_CSS = """
<style>

:root {
    --bg: #07111f;
    --panel: #0d1b2a;
    --panel2: #11243a;
    --border: rgba(255,255,255,.09);
    --text: #f4f7fb;
    --muted: #91a2b8;
    --green: #34d399;
    --blue: #60a5fa;
    --orange: #fbbf24;
    --red: #fb7185;
}

html,
body {
    margin: 0;
    padding: 0;
    min-height: 100%;
}

body {
    background:
        radial-gradient(
            circle at top right,
            rgba(59,130,246,.12),
            transparent 30%
        ),
        var(--bg);
    color: var(--text);
    font-family:
        Inter,
        ui-sans-serif,
        system-ui,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
    transition:
        background .25s ease,
        color .25s ease;
}

* {
    box-sizing: border-box;
}

a {
    color: inherit;
    text-decoration: none;
}

.app {
    min-height: 100vh;
    padding: 28px;
}

.container {
    max-width: 1400px;
    margin: auto;
}

.nav {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    margin-bottom: 32px;
}

.brand {
    display: flex;
    align-items: center;
    gap: 12px;
}

.logo {
    width: 44px;
    height: 44px;
    border-radius: 14px;
    display: grid;
    place-items: center;
    background: linear-gradient(
        135deg,
        #2563eb,
        #7c3aed
    );
    font-size: 21px;
    color: white;
}

.brand-title {
    font-size: 20px;
    font-weight: 800;
}

.brand-sub {
    color: var(--muted);
    font-size: 12px;
}

.nav-links {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
}

.nav-link {
    padding: 10px 14px;
    border-radius: 10px;
    color: var(--muted);
    cursor: pointer;
}

.nav-link:hover {
    background: rgba(255,255,255,.05);
    color: var(--text);
}

.theme-switch {
    display: flex;
    gap: 4px;
    padding: 4px;
    border-radius: 12px;
    border: 1px solid var(--border);
    background: rgba(255,255,255,.04);
}

.theme-btn {
    border: 0;
    padding: 8px 11px;
    border-radius: 8px;
    cursor: pointer;
    background: transparent;
    color: var(--muted);
    font-weight: 700;
}

.theme-btn.active {
    background: #2563eb;
    color: white;
}

h1 {
    margin: 0;
    font-size: 34px;
}

.subtitle {
    color: var(--muted);
    margin-top: 7px;
}

.grid {
    display: grid;
    grid-template-columns:
        repeat(4, minmax(0, 1fr));
    gap: 16px;
}

.card {
    background:
        linear-gradient(
            145deg,
            rgba(255,255,255,.055),
            rgba(255,255,255,.025)
        );
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 22px;
    box-shadow:
        0 15px 50px rgba(0,0,0,.18);
}

.metric-label {
    color: var(--muted);
    font-size: 13px;
}

.metric {
    margin-top: 8px;
    font-size: 28px;
    font-weight: 800;
}

.voice-card {
    margin-top: 18px;
    text-align: center;
    padding: 35px;
}

.voice-button {
    width: 105px;
    height: 105px;
    border-radius: 50%;
    border: none;
    cursor: pointer;
    font-size: 38px;
    background:
        linear-gradient(
            135deg,
            #2563eb,
            #7c3aed
        );
    color: white;
    box-shadow:
        0 0 0 10px rgba(96,165,250,.08),
        0 15px 40px rgba(37,99,235,.3);
}

.voice-button.recording {
    animation: pulse 1s infinite;
}

@keyframes pulse {
    0% {
        transform: scale(1);
    }
    50% {
        transform: scale(1.06);
    }
    100% {
        transform: scale(1);
    }
}

.voice-status {
    margin-top: 20px;
    font-weight: 700;
}

.voice-help {
    color: var(--muted);
    margin-top: 7px;
}

.section {
    margin-top: 22px;
}

.section-title {
    font-size: 18px;
    font-weight: 750;
    margin-bottom: 12px;
}

.table {
    width: 100%;
    border-collapse: collapse;
}

.table th,
.table td {
    text-align: left;
    padding: 13px;
    border-bottom: 1px solid var(--border);
}

.table th {
    color: var(--muted);
    font-size: 12px;
}

.badge {
    display: inline-flex;
    padding: 5px 9px;
    border-radius: 999px;
    background: rgba(96,165,250,.1);
    color: #93c5fd;
    font-size: 12px;
}

.form-grid {
    display: grid;
    grid-template-columns:
        repeat(2, minmax(0, 1fr));
    gap: 12px;
}

.input {
    width: 100%;
    padding: 13px 14px;
    border-radius: 11px;
    border: 1px solid var(--border);
    background: rgba(0,0,0,.18);
    color: var(--text);
    outline: none;
}

.input:focus {
    border-color: #60a5fa;
}

.checkbox-row {
    display: flex;
    align-items: center;
    gap: 9px;
    color: var(--muted);
    margin-top: 10px;
}

.primary-btn {
    border: 0;
    padding: 12px 18px;
    border-radius: 10px;
    background: #2563eb;
    color: white;
    cursor: pointer;
    font-weight: 700;
}

.secondary-btn {
    border: 1px solid var(--border);
    padding: 12px 18px;
    border-radius: 10px;
    background: rgba(255,255,255,.05);
    color: var(--text);
    cursor: pointer;
    font-weight: 700;
}

.danger-btn {
    border: 0;
    padding: 12px 18px;
    border-radius: 10px;
    background: #be123c;
    color: white;
    cursor: pointer;
    font-weight: 700;
}

.empty {
    color: var(--muted);
    padding: 25px 0;
}

.status-ok {
    color: #6ee7b7;
}

.status-error {
    color: #fda4af;
}

/* BRIGHT THEME */

body.bright {
    --bg: #f4f7fb;
    --panel: #ffffff;
    --panel2: #eef3f8;
    --border: rgba(15,23,42,.12);
    --text: #172033;
    --muted: #64748b;
}

body.bright {
    background:
        radial-gradient(
            circle at top right,
            rgba(59,130,246,.10),
            transparent 30%
        ),
        var(--bg);
}

body.bright .card {
    background: rgba(255,255,255,.88);
    box-shadow:
        0 15px 45px rgba(15,23,42,.08);
}

body.bright .input {
    background: white;
    color: #172033;
}

body.bright .theme-switch {
    background: rgba(15,23,42,.04);
}

body.bright .nav-link:hover {
    background: rgba(15,23,42,.05);
}

@media(max-width: 900px) {

    .grid {
        grid-template-columns:
            repeat(2, minmax(0, 1fr));
    }

}

@media(max-width: 600px) {

    .app {
        padding: 16px;
    }

    .grid {
        grid-template-columns: 1fr;
    }

    .form-grid {
        grid-template-columns: 1fr;
    }

    .nav {
        align-items: flex-start;
        flex-direction: column;
    }

}

</style>
"""


# ============================================================
# GLOBAL THEME SCRIPT
# ============================================================

THEME_SCRIPT = """
<script>

(function() {

    function applySavedTheme() {

        const theme =
            localStorage.getItem('hisabai-theme') ||
            'dark';

        if (theme === 'bright') {
            document.body.classList.add('bright');
        } else {
            document.body.classList.remove('bright');
        }

        document
            .querySelectorAll('.theme-btn')
            .forEach(btn => {

                btn.classList.toggle(
                    'active',
                    btn.dataset.theme === theme
                );

            });
    }

    window.setTheme = function(theme) {

        localStorage.setItem(
            'hisabai-theme',
            theme
        );

        if (theme === 'bright') {
            document.body.classList.add('bright');
        } else {
            document.body.classList.remove('bright');
        }

        document
            .querySelectorAll('.theme-btn')
            .forEach(btn => {

                btn.classList.toggle(
                    'active',
                    btn.dataset.theme === theme
                );

            });
    };

    window.addEventListener(
        'DOMContentLoaded',
        applySavedTheme
    );

    setTimeout(
        applySavedTheme,
        50
    );

})();

</script>
"""


# ============================================================
# NAVIGATION
# ============================================================

def navigation_html():

    return """
    <div class="nav">

        <div class="brand">

            <div class="logo">₹</div>

            <div>
                <div class="brand-title">
                    HisabAI
                </div>

                <div class="brand-sub">
                    Speak. Track. Collect.
                </div>
            </div>

        </div>

        <div class="nav-links">

            <a class="nav-link"
               href="/">
                Dashboard
            </a>

            <a class="nav-link"
               href="/customers">
                Customers
            </a>

            <a class="nav-link"
               href="/reminders">
                Reminders
            </a>

            <div class="theme-switch">

                <button
                    class="theme-btn"
                    data-theme="dark"
                    onclick="setTheme('dark')">
                    🌙 Dark
                </button>

                <button
                    class="theme-btn"
                    data-theme="bright"
                    onclick="setTheme('bright')">
                    ☀ Bright
                </button>

            </div>

        </div>

    </div>
    """


# ============================================================
# DASHBOARD HTML
# ============================================================

def dashboard_html():

    return """
    <div class="app">

        <div class="container">

            __NAV__

            <h1>
                Good business starts with clear hisab.
            </h1>

            <div class="subtitle">
                Speak your transaction. AI prepares the ledger.
            </div>

            <div class="grid"
                 style="margin-top:24px;">

                <div class="card">

                    <div class="metric-label">
                        Today's Sales
                    </div>

                    <div id="todaySales"
                         class="metric">
                        ₹0
                    </div>

                </div>

                <div class="card">

                    <div class="metric-label">
                        Received
                    </div>

                    <div id="received"
                         class="metric">
                        ₹0
                    </div>

                </div>

                <div class="card">

                    <div class="metric-label">
                        Outstanding
                    </div>

                    <div id="outstanding"
                         class="metric">
                        ₹0
                    </div>

                </div>

                <div class="card">

                    <div class="metric-label">
                        Customers
                    </div>

                    <div id="customersCount"
                         class="metric">
                        0
                    </div>

                </div>

            </div>

            <div class="card voice-card">

                <button
                    id="voiceButton"
                    class="voice-button"
                    onclick="startVoice()">
                    🎙️
                </button>

                <div
                    id="voiceStatus"
                    class="voice-status">
                    Tap to speak
                </div>

                <div class="voice-help">
                    Hindi • Marathi • English • Hinglish
                </div>

                <div
                    id="voiceResult"
                    style="margin-top:25px;">
                </div>

            </div>

            <div class="section">

                <div class="section-title">
                    Recent Transactions
                </div>

                <div class="card">

                    <table class="table">

                        <thead>

                            <tr>
                                <th>Customer</th>
                                <th>Item</th>
                                <th>Total</th>
                                <th>Paid</th>
                                <th>Outstanding</th>
                            </tr>

                        </thead>

                        <tbody id="transactionsBody">
                        </tbody>

                    </table>

                </div>

            </div>

        </div>

    </div>

    <script>

    async function loadDashboard() {

        try {

            const response =
                await fetch('/api/dashboard');

            const data =
                await response.json();

            if (!data.success) {
                throw new Error(
                    data.error || 'Dashboard error'
                );
            }

            const m = data.metrics;

            document.getElementById(
                'todaySales'
            ).textContent =
                '₹' + Number(
                    m.today_sales || 0
                ).toLocaleString('en-IN');

            document.getElementById(
                'received'
            ).textContent =
                '₹' + Number(
                    m.received || 0
                ).toLocaleString('en-IN');

            document.getElementById(
                'outstanding'
            ).textContent =
                '₹' + Number(
                    m.outstanding || 0
                ).toLocaleString('en-IN');

            document.getElementById(
                'customersCount'
            ).textContent =
                m.customers || 0;

            const body =
                document.getElementById(
                    'transactionsBody'
                );

            body.innerHTML = '';

            for (
                const t
                of data.recent_transactions || []
            ) {

                body.innerHTML += `
                    <tr>

                        <td>
                            ${escapeHtml(
                                t.customer || '-'
                            )}
                        </td>

                        <td>
                            ${escapeHtml(
                                t.item || '-'
                            )}
                        </td>

                        <td>
                            ₹${Number(
                                t.total_amount || 0
                            ).toLocaleString('en-IN')}
                        </td>

                        <td>
                            ₹${Number(
                                t.paid_amount || 0
                            ).toLocaleString('en-IN')}
                        </td>

                        <td>
                            ₹${Number(
                                t.outstanding_amount || 0
                            ).toLocaleString('en-IN')}
                        </td>

                    </tr>
                `;
            }

        } catch (error) {

            console.error(
                'Dashboard error:',
                error
            );
        }
    }


    function escapeHtml(value) {

        return String(value)
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#039;');

    }


    let mediaRecorder = null;
    let audioChunks = [];
    let recording = false;
    let voiceTimeout = null;


    async function startVoice() {

        const button =
            document.getElementById(
                'voiceButton'
            );

        const status =
            document.getElementById(
                'voiceStatus'
            );

        if (recording) {

            stopRecording();

            return;
        }

        if (
            !navigator.mediaDevices ||
            !navigator.mediaDevices.getUserMedia
        ) {

            status.textContent =
                'Your browser does not support microphone recording.';

            return;
        }

        try {

            const stream =
                await navigator.mediaDevices
                    .getUserMedia({
                        audio: true
                    });

            audioChunks = [];

            let mimeType = '';

            if (
                MediaRecorder.isTypeSupported(
                    'audio/webm;codecs=opus'
                )
            ) {

                mimeType =
                    'audio/webm;codecs=opus';

            } else if (
                MediaRecorder.isTypeSupported(
                    'audio/webm'
                )
            ) {

                mimeType =
                    'audio/webm';

            }

            mediaRecorder =
                mimeType
                    ? new MediaRecorder(
                        stream,
                        { mimeType }
                    )
                    : new MediaRecorder(
                        stream
                    );

            mediaRecorder.ondataavailable =
                event => {

                    if (
                        event.data &&
                        event.data.size > 0
                    ) {

                        audioChunks.push(
                            event.data
                        );
                    }
                };


            mediaRecorder.onerror =
                event => {

                    console.error(
                        'Recorder error:',
                        event
                    );

                    stream
                        .getTracks()
                        .forEach(
                            track =>
                                track.stop()
                        );

                    recording = false;

                    button.textContent = '🎙️';
                    button.classList.remove(
                        'recording'
                    );

                    status.textContent =
                        'Recording error. Please try again.';
                };


            mediaRecorder.onstop =
                async () => {

                    stream
                        .getTracks()
                        .forEach(
                            track =>
                                track.stop()
                        );

                    const finalType =
                        mimeType ||
                        'audio/webm';

                    const blob =
                        new Blob(
                            audioChunks,
                            {
                                type: finalType
                            }
                        );

                    if (blob.size < 1000) {

                        status.textContent =
                            'No voice captured. Please speak clearly and try again.';

                        return;
                    }

                    await uploadVoice(
                        blob,
                        finalType
                    );
                };


            mediaRecorder.start(
                250
            );

            recording = true;

            button.textContent = '⏹️';

            button.classList.add(
                'recording'
            );

            status.textContent =
                'Listening... Speak now';

            voiceTimeout =
                setTimeout(
                    () => {

                        if (recording) {
                            stopRecording();
                        }

                    },
                    10000
                );

        } catch (error) {

            console.error(
                'Microphone error:',
                error
            );

            status.textContent =
                'Microphone permission required';

            recording = false;

            button.textContent = '🎙️';

            button.classList.remove(
                'recording'
            );
        }
    }


    function stopRecording() {

        if (voiceTimeout) {

            clearTimeout(
                voiceTimeout
            );

            voiceTimeout = null;
        }

        if (
            mediaRecorder &&
            mediaRecorder.state !== 'inactive'
        ) {

            mediaRecorder.stop();
        }

        recording = false;

        const button =
            document.getElementById(
                'voiceButton'
            );

        button.textContent = '🎙️';

        button.classList.remove(
            'recording'
        );

        const status =
            document.getElementById(
                'voiceStatus'
            );

        status.textContent =
            'Processing with AI...';
    }


    async function uploadVoice(
        blob,
        mimeType
    ) {

        const status =
            document.getElementById(
                'voiceStatus'
            );

        const resultBox =
            document.getElementById(
                'voiceResult'
            );

        try {

            const extension =
                mimeType.includes('webm')
                    ? 'webm'
                    : 'webm';

            const formData =
                new FormData();

            formData.append(
                'file',
                blob,
                'voice.' + extension
            );

            const response =
                await fetch(
                    '/api/process_voice_note',
                    {
                        method: 'POST',
                        body: formData
                    }
                );

            const text =
                await response.text();

            let data;

            try {

                data = JSON.parse(text);

            } catch {

                throw new Error(
                    text ||
                    'Server returned invalid response.'
                );
            }

            if (
                !response.ok ||
                data.success === false
            ) {

                throw new Error(
                    data.error ||
                    data.detail ||
                    'Voice processing failed.'
                );
            }

            const transaction =
                data.transaction ||
                data;

            resultBox.innerHTML = `

                <div class="card"
                     style="text-align:left;">

                    <div class="section-title">
                        AI Transaction Preview
                    </div>

                    <p>
                        <b>Customer:</b>
                        ${escapeHtml(
                            transaction.customer_name ||
                            transaction.customer ||
                            '-'
                        )}
                    </p>

                    <p>
                        <b>Item:</b>
                        ${escapeHtml(
                            transaction.item ||
                            '-'
                        )}
                    </p>

                    <p>
                        <b>Total:</b>
                        ₹${Number(
                            transaction.total_amount || 0
                        ).toLocaleString('en-IN')}
                    </p>

                    <p>
                        <b>Paid:</b>
                        ₹${Number(
                            transaction.paid_amount || 0
                        ).toLocaleString('en-IN')}
                    </p>

                    <p>
                        <b>Outstanding:</b>
                        ₹${Number(
                            transaction.outstanding_amount || 0
                        ).toLocaleString('en-IN')}
                    </p>

                    <div style="margin-top:18px;">

                        <label>
                            <b>
                                Customer phone number
                            </b>
                        </label>

                        <input
                            id="voicePhone"
                            class="input"
                            style="margin-top:7px;"
                            placeholder="+91 9876543210"
                            type="tel"
                        />

                    </div>

                    <button
                        onclick='confirmVoiceTransaction(${JSON.stringify(
                            transaction
                        )})'
                        class="primary-btn"
                        style="margin-top:15px;"
                    >
                        ✓ Confirm & Save
                    </button>

                </div>
            `;

            status.textContent =
                'AI understood your transaction';

        } catch (error) {

            console.error(error);

            status.textContent =
                'Voice processing failed';

            resultBox.innerHTML = `

                <div class="card">

                    <div class="status-error">
                        ${escapeHtml(
                            error.message
                        )}
                    </div>

                </div>
            `;
        }
    }


    async function confirmVoiceTransaction(
        transaction
    ) {

        try {

            const phoneInput =
                document.getElementById(
                    'voicePhone'
                );

            const phone =
                phoneInput
                    ? phoneInput.value.trim()
                    : '';

            const response =
                await fetch(
                    '/api/transactions/confirm',
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type':
                                'application/json'
                        },
                        body: JSON.stringify({

                            customer:
                                transaction.customer_name ||
                                transaction.customer ||
                                '',

                            phone:
                                phone || null,

                            item:
                                transaction.item ||
                                null,

                            transaction_type:
                                transaction.intent ||
                                'sale',

                            total_amount:
                                Number(
                                    transaction.total_amount ||
                                    0
                                ),

                            paid_amount:
                                Number(
                                    transaction.paid_amount ||
                                    0
                                ),

                            payment_method:
                                transaction.payment_method ||
                                null,

                            due_date:
                                transaction.due_date ||
                                null,

                            payment_status:
                                transaction.payment_status ||
                                null,

                            detected_language:
                                transaction.language ||
                                transaction.detected_language ||
                                null,

                            confidence:
                                Number(
                                    transaction.confidence ||
                                    0
                                ),

                            raw_transcript:
                                transaction.transcript ||
                                transaction.raw_transcript ||
                                null
                        })
                    }
                );

            const text =
                await response.text();

            let data;

            try {
                data = JSON.parse(text);
            } catch {

                throw new Error(
                    text ||
                    'Invalid server response.'
                );
            }

            if (
                !response.ok ||
                data.success === false
            ) {

                throw new Error(
                    data.error ||
                    data.detail ||
                    'Could not save transaction.'
                );
            }

            document.getElementById(
                'voiceStatus'
            ).textContent =
                'Transaction saved ✓';

            document.getElementById(
                'voiceResult'
            ).innerHTML = `

                <div style="
                    padding:16px;
                    border-radius:12px;
                    background:rgba(52,211,153,.1);
                    color:#6ee7b7;
                ">
                    Transaction saved successfully.
                    ${phone
                        ? '<br>Phone number saved ✓'
                        : ''}
                </div>
            `;

            await loadDashboard();

        } catch (error) {

            console.error(error);

            document.getElementById(
                'voiceStatus'
            ).textContent =
                error.message;
        }
    }


    loadDashboard();

    </script>
    """


# ============================================================
# CUSTOMERS HTML
# ============================================================

def customers_html():

    return """
    <div class="app">

        <div class="container">

            __NAV__

            <h1>Customers</h1>

            <div class="subtitle">
                Manage customers, phone numbers and reminder consent.
            </div>

            <div class="card"
                 style="margin-top:24px;">

                <div class="section-title">
                    Add Customer
                </div>

                <div class="form-grid">

                    <input
                        id="newCustomerName"
                        class="input"
                        placeholder="Customer name"
                    />

                    <input
                        id="newCustomerPhone"
                        class="input"
                        placeholder="+91 9876543210"
                        type="tel"
                    />

                </div>

                <div class="checkbox-row">

                    <input
                        id="newReminderEnabled"
                        type="checkbox"
                    />

                    <label for="newReminderEnabled">
                        Enable payment reminders
                    </label>

                </div>

                <div class="checkbox-row">

                    <input
                        id="newReminderConsent"
                        type="checkbox"
                    />

                    <label for="newReminderConsent">
                        Customer has given reminder consent
                    </label>

                </div>

                <button
                    class="primary-btn"
                    style="margin-top:15px;"
                    onclick="addCustomer()">
                    + Add Customer
                </button>

                <div
                    id="addCustomerResult"
                    style="margin-top:12px;">
                </div>

            </div>


            <div
                id="customersList"
                class="grid"
                style="margin-top:24px;">
            </div>

        </div>

    </div>


    <script>

    async function addCustomer() {

        const name =
            document.getElementById(
                'newCustomerName'
            ).value.trim();

        const phone =
            document.getElementById(
                'newCustomerPhone'
            ).value.trim();

        const reminderEnabled =
            document.getElementById(
                'newReminderEnabled'
            ).checked;

        const reminderConsent =
            document.getElementById(
                'newReminderConsent'
            ).checked;

        const result =
            document.getElementById(
                'addCustomerResult'
            );

        if (!name) {

            result.innerHTML =
                '<div class="status-error">Customer name is required.</div>';

            return;
        }

        try {

            const response =
                await fetch(
                    '/api/customers',
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type':
                                'application/json'
                        },
                        body: JSON.stringify({

                            name: name,

                            phone:
                                phone || null,

                            preferred_reminder_language:
                                'hindi',

                            reminder_enabled:
                                reminderEnabled,

                            reminder_consent:
                                reminderConsent

                        })
                    }
                );

            const data =
                await response.json();

            if (
                !response.ok ||
                data.success === false
            ) {

                throw new Error(
                    data.error ||
                    'Could not create customer.'
                );
            }

            result.innerHTML =
                '<div class="status-ok">✓ Customer saved successfully.</div>';

            document.getElementById(
                'newCustomerName'
            ).value = '';

            document.getElementById(
                'newCustomerPhone'
            ).value = '';

            document.getElementById(
                'newReminderEnabled'
            ).checked = false;

            document.getElementById(
                'newReminderConsent'
            ).checked = false;

            loadCustomers();

        } catch (error) {

            result.innerHTML =
                '<div class="status-error">' +
                escapeHtml(error.message) +
                '</div>';
        }
    }


    async function updateCustomer(
        customerId
    ) {

        const name =
            document.getElementById(
                'name-' + customerId
            ).value.trim();

        const phone =
            document.getElementById(
                'phone-' + customerId
            ).value.trim();

        const enabled =
            document.getElementById(
                'enabled-' + customerId
            ).checked;

        const consent =
            document.getElementById(
                'consent-' + customerId
            ).checked;

        const language =
            document.getElementById(
                'language-' + customerId
            ).value;

        const result =
            document.getElementById(
                'result-' + customerId
            );

        try {

            const response =
                await fetch(
                    '/api/customers/' +
                    customerId,
                    {
                        method: 'PUT',
                        headers: {
                            'Content-Type':
                                'application/json'
                        },
                        body: JSON.stringify({

                            name: name,

                            phone:
                                phone || null,

                            preferred_reminder_language:
                                language,

                            reminder_enabled:
                                enabled,

                            reminder_consent:
                                consent,

                            reminder_frequency_days:
                                3

                        })
                    }
                );

            const data =
                await response.json();

            if (
                !response.ok ||
                data.success === false
            ) {

                throw new Error(
                    data.error ||
                    'Could not update customer.'
                );
            }

            result.innerHTML =
                '<div class="status-ok">✓ Saved</div>';

            setTimeout(
                () => {
                    result.innerHTML = '';
                },
                2500
            );

            loadCustomers();

        } catch (error) {

            result.innerHTML =
                '<div class="status-error">' +
                escapeHtml(error.message) +
                '</div>';
        }
    }


    async function loadCustomers() {

        const container =
            document.getElementById(
                'customersList'
            );

        try {

            const response =
                await fetch(
                    '/api/customers'
                );

            const data =
                await response.json();

            if (!data.success) {

                throw new Error(
                    data.error ||
                    'Could not load customers.'
                );
            }

            container.innerHTML = '';

            for (
                const customer
                of data.customers || []
            ) {

                const enabled =
                    customer.reminder_enabled
                    ? 'checked'
                    : '';

                const consent =
                    customer.reminder_consent
                    ? 'checked'
                    : '';

                const language =
                    customer.preferred_reminder_language ||
                    'hindi';

                container.innerHTML += `

                    <div class="card">

                        <div style="
                            font-size:18px;
                            font-weight:800;
                        ">
                            ${escapeHtml(
                                customer.name
                            )}
                        </div>

                        <div
                            style="
                                margin-top:12px;
                                color:var(--muted);
                            "
                        >
                            Outstanding
                        </div>

                        <div class="metric">
                            ₹${Number(
                                customer.outstanding_amount || 0
                            ).toLocaleString('en-IN')}
                        </div>


                        <div style="
                            margin-top:20px;
                        ">

                            <label>
                                Customer name
                            </label>

                            <input
                                id="name-${customer.id}"
                                class="input"
                                style="margin-top:5px;"
                                value="${escapeHtml(
                                    customer.name || ''
                                )}"
                            />

                        </div>


                        <div style="
                            margin-top:12px;
                        ">

                            <label>
                                Phone number
                            </label>

                            <input
                                id="phone-${customer.id}"
                                class="input"
                                style="margin-top:5px;"
                                type="tel"
                                placeholder="+91 9876543210"
                                value="${escapeHtml(
                                    customer.phone || ''
                                )}"
                            />

                        </div>


                        <div style="
                            margin-top:12px;
                        ">

                            <label>
                                Reminder language
                            </label>

                            <select
                                id="language-${customer.id}"
                                class="input"
                                style="margin-top:5px;"
                            >

                                <option
                                    value="hindi"
                                    ${language === 'hindi'
                                        ? 'selected'
                                        : ''}>
                                    Hindi
                                </option>

                                <option
                                    value="marathi"
                                    ${language === 'marathi'
                                        ? 'selected'
                                        : ''}>
                                    Marathi
                                </option>

                                <option
                                    value="english"
                                    ${language === 'english'
                                        ? 'selected'
                                        : ''}>
                                    English
                                </option>

                            </select>

                        </div>


                        <div class="checkbox-row">

                            <input
                                id="enabled-${customer.id}"
                                type="checkbox"
                                ${enabled}
                            />

                            <label
                                for="enabled-${customer.id}">
                                Enable reminders
                            </label>

                        </div>


                        <div class="checkbox-row">

                            <input
                                id="consent-${customer.id}"
                                type="checkbox"
                                ${consent}
                            />

                            <label
                                for="consent-${customer.id}">
                                Customer gave consent
                            </label>

                        </div>


                        <button
                            class="primary-btn"
                            style="margin-top:15px;"
                            onclick="updateCustomer(${customer.id})">
                            Save Changes
                        </button>


                        <div
                            id="result-${customer.id}"
                            style="margin-top:10px;">
                        </div>


                        <div style="
                            margin-top:15px;
                            padding:10px;
                            border-radius:10px;
                            background:rgba(96,165,250,.08);
                            font-size:12px;
                            color:var(--muted);
                        ">

                            ${customer.reminder_enabled &&
                              customer.reminder_consent
                                ? '🟢 Ready for reminders'
                                : '⚪ Reminders disabled'}

                        </div>

                    </div>
                `;
            }


            if (
                !data.customers ||
                data.customers.length === 0
            ) {

                container.innerHTML =
                    '<div class="empty">No customers yet.</div>';
            }

        } catch (error) {

            container.innerHTML = `

                <div class="card">

                    <div class="status-error">
                        ${escapeHtml(
                            error.message
                        )}
                    </div>

                </div>

            `;
        }
    }


    function escapeHtml(value) {

        return String(value)
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#039;');

    }


    loadCustomers();

    </script>
    """


# ============================================================
# REMINDERS HTML
# ============================================================

def reminders_html():

    return """
    <div class="app">

        <div class="container">

            __NAV__

            <h1>
                Payment Reminders
            </h1>

            <div class="subtitle">
                AI-powered consent-aware voice collection.
            </div>

            <div
                id="reminderList"
                style="margin-top:24px;">
            </div>

        </div>

    </div>


    <script>

    async function loadReminders() {

        const container =
            document.getElementById(
                'reminderList'
            );

        try {

            const response =
                await fetch(
                    '/api/reminder-candidates'
                );

            const data =
                await response.json();

            if (!data.success) {

                throw new Error(
                    data.error ||
                    'Could not load reminders.'
                );
            }

            container.innerHTML = '';

            for (
                const candidate
                of data.candidates || []
            ) {

                const customerId =
                    candidate.customer_id ||
                    candidate.id;

                const enabled =
                    candidate.reminder_enabled;

                const consent =
                    candidate.reminder_consent;

                container.innerHTML += `

                    <div class="card"
                         style="margin-bottom:15px;">

                        <div style="
                            display:flex;
                            justify-content:space-between;
                            gap:20px;
                            align-items:center;
                            flex-wrap:wrap;
                        ">

                            <div>

                                <div style="
                                    font-size:19px;
                                    font-weight:800;
                                ">
                                    ${escapeHtml(
                                        candidate.customer_name ||
                                        candidate.name ||
                                        'Customer'
                                    )}
                                </div>

                                <div style="
                                    color:var(--muted);
                                    margin-top:6px;
                                ">

                                    Outstanding:

                                    <b>
                                        ₹${Number(
                                            candidate.outstanding_amount || 0
                                        ).toLocaleString('en-IN')}
                                    </b>

                                </div>

                                <div style="
                                    margin-top:8px;
                                    font-size:12px;
                                    color:var(--muted);
                                ">

                                    ${candidate.phone
                                        ? '📱 ' +
                                          escapeHtml(candidate.phone)
                                        : '⚠ No phone number'}

                                </div>

                            </div>


                            <button
                                onclick="sendReminder(${customerId}, false)"
                                class="primary-btn">

                                📞 Send Reminder

                            </button>

                        </div>


                        <div
                            id="reminderResult-${customerId}"
                            style="margin-top:12px;">
                        </div>

                    </div>
                `;
            }


            if (
                !data.candidates ||
                data.candidates.length === 0
            ) {

                container.innerHTML = `

                    <div class="card">

                        <div class="empty">

                            No customers currently need
                            a payment reminder.

                        </div>

                        <div style="
                            margin-top:12px;
                            color:var(--muted);
                            font-size:13px;
                        ">

                            Go to Customers → enable
                            reminders + consent for
                            customers with outstanding payments.

                        </div>

                    </div>

                `;
            }

        } catch (error) {

            container.innerHTML = `

                <div class="card">

                    <div class="status-error">
                        ${escapeHtml(
                            error.message
                        )}
                    </div>

                </div>

            `;
        }
    }


    async function sendReminder(
        customerId,
        enableReminders = false
    ) {

        const resultBox =
            document.getElementById(
                'reminderResult-' +
                customerId
            );

        resultBox.innerHTML =
            '<div style="color:var(--muted);">Starting reminder...</div>';

        try {

            const response =
                await fetch(
                    '/api/customers/' +
                    customerId +
                    '/reminder',
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type':
                                'application/json'
                        },
                        body: JSON.stringify({
                            force: true,
                            enable_reminders:
                                enableReminders
                        })
                    }
                );

            const text =
                await response.text();

            let data;

            try {
                data = JSON.parse(text);
            } catch {
                throw new Error(
                    `Server returned ${response.status}: ${text}`
                );
            }

            if (
                data.error_type ===
                'REMINDERS_DISABLED'
            ) {
                resultBox.innerHTML = `
                    <div style="
                        padding:15px;
                        border-radius:12px;
                        background:rgba(251,191,36,.10);
                        border:1px solid rgba(251,191,36,.25);
                    ">
                        <div style="font-weight:800;color:#fbbf24;">
                            🔔 Reminders are disabled
                        </div>
                        <div style="margin-top:7px;color:var(--muted);">
                            Enable reminder consent before sending a voice reminder.
                        </div>
                        <button
                            class="primary-btn"
                            style="margin-top:12px;"
                            onclick="sendReminder(${customerId}, true)"
                        >
                            🔔 Enable & Send Reminder
                        </button>
                    </div>
                `;
                return;
            }

            if (
                data.error_type ===
                'TWILIO_TRIAL_RESTRICTION'
            ) {
                resultBox.innerHTML = `
                    <div style="
                        padding:16px;
                        border-radius:12px;
                        background:rgba(251,191,36,.10);
                        border:1px solid rgba(251,191,36,.25);
                    ">
                        <div style="font-size:16px;font-weight:800;color:#fbbf24;">
                            📞 Reminder processed
                        </div>
                        <div style="margin-top:8px;color:var(--text);">
                            ⚠️ Voice call could not be placed.
                        </div>
                        <div style="margin-top:7px;font-size:13px;color:var(--muted);line-height:1.5;">
                            Twilio is currently on a trial account and is restricting this outgoing application call.
                        </div>
                        <div style="margin-top:10px;font-size:13px;color:#6ee7b7;">
                            ✓ HisabAI reminder logic is working.
                        </div>
                    </div>
                `;
                return;
            }

            if (
                response.ok &&
                data.success === true
            ) {
                const reminder = data.reminder || {};
                resultBox.innerHTML = `
                    <div style="
                        padding:14px;
                        border-radius:12px;
                        background:rgba(52,211,153,.1);
                        color:#6ee7b7;
                    ">
                        ✓ ${escapeHtml(
                            data.message ||
                            'Reminder sent.'
                        )}
                        <div style="margin-top:5px;font-size:12px;">
                            Status: ${escapeHtml(
                                reminder.status || 'queued'
                            )}
                        </div>
                    </div>
                `;
                return;
            }

            resultBox.innerHTML = `
                <div style="
                    padding:14px;
                    border-radius:12px;
                    background:rgba(251,113,133,.1);
                    color:#fda4af;
                ">
                    ❌ ${escapeHtml(
                        data.user_message ||
                        data.message ||
                        data.error ||
                        'Could not send reminder.'
                    )}
                </div>
            `;

        } catch (error) {

            console.error(
                'Reminder error:',
                error
            );

            resultBox.innerHTML = `
                <div style="
                    padding:14px;
                    border-radius:12px;
                    background:rgba(251,113,133,.1);
                    color:#fda4af;
                ">
                    ❌ ${escapeHtml(error.message)}
                </div>
            `;
        }
    }

    function escapeHtml(value) {

        return String(value)
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#039;');

    }


    loadReminders();

    </script>
    """


# ============================================================
# NICEGUI PAGES
# ============================================================

def setup_page(
    html: str,
):

    ui.add_head_html(APP_CSS)

    ui.add_body_html(
        html
    )

    ui.add_body_html(
        THEME_SCRIPT
    )


@ui.page("/")
def dashboard_page():

    setup_page(
        dashboard_html().replace(
            "__NAV__",
            navigation_html(),
        )
    )


@ui.page("/customers")
def customers_page():

    setup_page(
        customers_html().replace(
            "__NAV__",
            navigation_html(),
        )
    )


@ui.page("/reminders")
def reminders_page():

    setup_page(
        reminders_html().replace(
            "__NAV__",
            navigation_html(),
        )
    )


# ============================================================
# START SERVER
# ============================================================

ui.run_with(
    fastapi_app,
    title="HisabAI — Voice Ledger",
)

if __name__ in {
    "__main__",
    "__mp_main__",
}:

    import uvicorn

    uvicorn.run(
        fastapi_app,
        host=HOST,
        port=PORT,
        workers=1,
    )