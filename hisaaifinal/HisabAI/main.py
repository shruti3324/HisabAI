from __future__ import annotations

import asyncio
import json
import os
import re
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


def parse_items(value: Any, fallback: Optional[str] = None) -> list[str]:
    """Return transaction items as a clean list, supporting JSON/list/text data."""
    if isinstance(value, list):
        raw = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            decoded = json.loads(text)
            raw = decoded if isinstance(decoded, list) else [decoded]
        except Exception:
            raw = text.replace("\r", "\n").replace(",", "\n").split("\n")
    elif value is not None:
        raw = [value]
    elif fallback:
        raw = fallback.replace("\r", "\n").replace(",", "\n").split("\n")
    else:
        raw = []

    result = []
    for item in raw:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def transaction_to_dict(
    transaction: Transaction,
) -> dict:

    return {
        "id": transaction.id,
        "customer_id": transaction.customer_id,
        "customer": transaction.customer,
        "transaction_type": transaction.transaction_type,
        "item": transaction.item,
        "items": parse_items(transaction.items_json, transaction.item),
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
    items: Optional[list[str]] = None
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

        item_list = parse_items(payload.items, payload.item)
        item_text = ", ".join(item_list) if item_list else None

        transaction = Transaction(
            user_id=USER_ID,
            customer_id=customer.id,
            customer=customer.name,
            transaction_type=(
                payload.transaction_type or "sale"
            ),
            item=item_text,
            items_json=json.dumps(item_list, ensure_ascii=False),
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


@fastapi_app.delete("/api/customers/{customer_id}")
async def delete_customer(customer_id: int):
    with get_session() as session:
        customer = session.get(Customer, customer_id)
        if not customer or customer.user_id != USER_ID:
            raise HTTPException(status_code=404, detail="Customer not found.")
        transactions = session.exec(select(Transaction).where(
            Transaction.user_id == USER_ID,
            Transaction.customer_id == customer_id,
            Transaction.status == "active",
        )).all()
        if transactions:
            raise HTTPException(status_code=409, detail="This customer has transactions and cannot be deleted. Update the customer instead.")
        session.delete(customer)
        session.commit()
        return {"success": True, "message": "Customer deleted."}


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

body.light {
    --bg: #f4f7fb;
    --panel: #ffffff;
    --panel2: #eef3f8;
    --border: rgba(15,23,42,.12);
    --text: #172033;
    --muted: #64748b;
}

body.light {
    background:
        radial-gradient(
            circle at top right,
            rgba(59,130,246,.10),
            transparent 30%
        ),
        var(--bg);
}

body.light .card {
    background: rgba(255,255,255,.88);
    box-shadow:
        0 15px 45px rgba(15,23,42,.08);
}

body.light .input {
    background: white;
    color: #172033;
}

body.light .theme-switch {
    background: rgba(15,23,42,.04);
}

body.light .nav-link:hover {
    background: rgba(15,23,42,.05);
}

.pagination { display:flex; justify-content:flex-end; gap:10px; margin-top:16px; }
.secondary-btn:disabled { opacity:.45; cursor:not-allowed; }
.customer-row { display:flex; justify-content:space-between; align-items:center; gap:18px; margin-bottom:12px; }
.customer-meta { color:var(--muted); margin-top:7px; font-size:13px; }
.customer-actions { display:flex; gap:8px; flex-wrap:wrap; }
.manual-card { margin-top:18px; }

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

        if (theme === 'light') {
            document.body.classList.add('light');
        } else {
            document.body.classList.remove('light');
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

        if (theme === 'light') {
            document.body.classList.add('light');
        } else {
            document.body.classList.remove('light');
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

    // Shared helper used by Home and Dashboard transaction tables.
    window.formatItems = function(items, fallback) {
        let values = [];
        if (Array.isArray(items)) {
            values = items;
        } else if (items !== undefined && items !== null && String(items).trim()) {
            try {
                const parsed = JSON.parse(String(items));
                values = Array.isArray(parsed) ? parsed : [parsed];
            } catch (e) {
                values = String(items).split(/[,\n]+/);
            }
        } else if (fallback) {
            values = String(fallback).split(/[,\n]+/);
        }
        values = values.map(v => String(v).trim()).filter(Boolean);
        if (!values.length) return '—';
        const esc = v => String(v)
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#039;');
        return '<ul style="margin:0;padding-left:18px;">' +
            values.map(v => '<li>' + esc(v) + '</li>').join('') +
            '</ul>';
    };

})();

</script>
"""


# ============================================================
# NAVIGATION
# ============================================================

def navigation_html():
    return """
    <div class="nav">
        <div class="brand"><div class="logo">₹</div><div><div class="brand-title">HisabAI</div><div class="brand-sub">Speak. Track. Collect.</div></div></div>
        <div class="nav-links">
            <a class="nav-link" href="/">Home</a>
            <a class="nav-link" href="/dashboard">Dashboard</a>
            <a class="nav-link" href="/customers">Customers</a>
            <a class="nav-link" href="/reminders">Reminders</a>
            <div class="theme-switch">
                <button class="theme-btn" data-theme="dark" onclick="setTheme('dark')">🌙 Dark</button>
                <button class="theme-btn" data-theme="light" onclick="setTheme('light')">☀ Light</button>
            </div>
        </div>
    </div>
    """


# ============================================================
# DASHBOARD HTML
# ============================================================

def dashboard_html():
    return """
    <div class="app"><div class="container">__NAV__
        <h1>Business Dashboard</h1><div class="subtitle">A clear view of today's sales, collections and outstanding udhaar.</div>
        <div class="grid" style="margin-top:24px;">
            <div class="card"><div class="metric-label">Today's Sales</div><div id="dashTodaySales" class="metric">₹0</div></div>
            <div class="card"><div class="metric-label">Received</div><div id="dashReceived" class="metric">₹0</div></div>
            <div class="card"><div class="metric-label">Outstanding</div><div id="dashOutstanding" class="metric">₹0</div></div>
            <div class="card"><div class="metric-label">Customers</div><div id="dashCustomers" class="metric">0</div></div>
        </div>
        <div class="section"><div class="section-title">Recent Activity</div><div class="card"><div style="overflow-x:auto;"><table class="table"><thead><tr><th>Customer</th><th>Items</th><th>Total</th><th>Paid</th><th>Outstanding</th></tr></thead><tbody id="dashboardTransactions"></tbody></table></div></div></div>
    </div></div>
    <script>
    function escapeHtml(v){return String(v).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;');}
    async function loadBusinessDashboard(){try{const r=await fetch('/api/dashboard');const d=await r.json();if(!d.success)throw new Error(d.error||'Dashboard error');const m=d.metrics||{};document.getElementById('dashTodaySales').textContent='₹'+Number(m.today_sales||0).toLocaleString('en-IN');document.getElementById('dashReceived').textContent='₹'+Number(m.received||0).toLocaleString('en-IN');document.getElementById('dashOutstanding').textContent='₹'+Number(m.outstanding||0).toLocaleString('en-IN');document.getElementById('dashCustomers').textContent=m.customers||0;const b=document.getElementById('dashboardTransactions');b.innerHTML=(d.recent_transactions||[]).map(t=>`<tr><td>${escapeHtml(t.customer||'-')}</td><td>${formatItems(t.items,t.item)}</td><td>₹${Number(t.total_amount||0).toLocaleString('en-IN')}</td><td>₹${Number(t.paid_amount||0).toLocaleString('en-IN')}</td><td>₹${Number(t.outstanding_amount||0).toLocaleString('en-IN')}</td></tr>`).join('');if(!b.innerHTML)b.innerHTML='<tr><td colspan="5" class="empty">No transactions yet.</td></tr>';}catch(e){console.error(e)}}loadBusinessDashboard();
    </script>"""


def home_html():
    return """
    <div class="app"><div class="container">__NAV__
        <h1>Good business starts with clear hisab.</h1><div class="subtitle">Speak your transaction. AI prepares the ledger.</div>
        <div class="card voice-card" style="margin-top:24px;"><button id="voiceButton" type="button" class="voice-button" onclick="window.startVoice && window.startVoice(); return false;">🎙️</button><div id="voiceStatus" class="voice-status">Tap to speak</div><div class="voice-help">Hindi • Marathi • English • Hinglish</div><div id="voiceResult" style="margin-top:25px;"></div></div>
        <div class="card manual-card"><div class="section-title">Manual Entry</div><div class="subtitle" style="margin-bottom:14px;">Add a transaction without voice.</div><div class="form-grid"><input id="manualCustomer" class="input" placeholder="Customer name"><textarea id="manualItems" class="input" rows="3" placeholder="Items (one per line or comma separated)"></textarea><input id="manualTotal" class="input" type="number" min="0" step="0.01" placeholder="Total amount (₹)"><input id="manualPaid" class="input" type="number" min="0" step="0.01" placeholder="Paid amount (₹)"><input id="manualPhone" class="input" type="tel" placeholder="Phone (optional)"><input id="manualDueDate" class="input" type="date" title="Due date (optional)"></div><button class="primary-btn" style="margin-top:15px;" onclick="saveManualEntry()">✓ Save Transaction</button><div id="manualResult" style="margin-top:12px;"></div></div>
        <div class="section"><div class="section-title" style="display:flex;justify-content:space-between;align-items:center;"><span>Recent Transactions</span><span id="pageInfo" class="badge">Page 1</span></div><div class="card"><div style="overflow-x:auto;"><table class="table"><thead><tr><th>Customer</th><th>Items</th><th>Total</th><th>Paid</th><th>Outstanding</th></tr></thead><tbody id="transactionsBody"></tbody></table></div><div class="pagination"><button id="prevPage" class="secondary-btn" onclick="changePage(-1)">← Previous</button><button id="nextPage" class="secondary-btn" onclick="changePage(1)">Next →</button></div></div></div>
    </div></div>
    <script>
    let allTransactions=[],currentPage=1;const pageSize=5;
    function escapeHtml(v){return String(v).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;');}
    function renderTransactions(){const b=document.getElementById('transactionsBody'),pages=Math.max(1,Math.ceil(allTransactions.length/pageSize));currentPage=Math.min(currentPage,pages);const rows=allTransactions.slice((currentPage-1)*pageSize,currentPage*pageSize);b.innerHTML=rows.map(t=>`<tr><td>${escapeHtml(t.customer||'-')}</td><td>${formatItems(t.items,t.item)}</td><td>₹${Number(t.total_amount||0).toLocaleString('en-IN')}</td><td>₹${Number(t.paid_amount||0).toLocaleString('en-IN')}</td><td>₹${Number(t.outstanding_amount||0).toLocaleString('en-IN')}</td></tr>`).join('');if(!b.innerHTML)b.innerHTML='<tr><td colspan="5" class="empty">No transactions yet.</td></tr>';document.getElementById('pageInfo').textContent=`Page ${currentPage} of ${pages}`;document.getElementById('prevPage').disabled=currentPage<=1;document.getElementById('nextPage').disabled=currentPage>=pages;}
    function changePage(d){currentPage+=d;renderTransactions();}
    async function loadHome(){try{const r=await fetch('/api/transactions');const d=await r.json();if(!d.success)throw new Error(d.error||'Could not load transactions.');allTransactions=d.transactions||[];renderTransactions();}catch(e){document.getElementById('transactionsBody').innerHTML=`<tr><td colspan="5" class="status-error">${escapeHtml(e.message)}</td></tr>`;}}
    async function saveManualEntry(){const result=document.getElementById('manualResult'),customer=document.getElementById('manualCustomer').value.trim(),itemsText=document.getElementById('manualItems').value.trim(),items=itemsText.split(/[,\n]+/).map(x=>x.trim()).filter(Boolean),total=Number(document.getElementById('manualTotal').value||0),paid=Number(document.getElementById('manualPaid').value||0),phone=document.getElementById('manualPhone').value.trim(),dueDate=document.getElementById('manualDueDate').value||null;if(!customer){result.innerHTML='<div class="status-error">Customer name is required.</div>';return;}if(total<=0){result.innerHTML='<div class="status-error">Enter a valid total amount.</div>';return;}if(paid<0||paid>total){result.innerHTML='<div class="status-error">Paid amount must be between ₹0 and the total.</div>';return;}try{const r=await fetch('/api/transactions/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({customer,phone:phone||null,item:items[0]||null,items:items,transaction_type:'sale',total_amount:total,paid_amount:paid,due_date:dueDate,payment_status:paid>=total?'paid':(paid>0?'partial':'pending')})});const d=await r.json();if(!r.ok||d.success===false)throw new Error(d.error||d.detail||'Could not save transaction.');result.innerHTML='<div class="status-ok">✓ Transaction saved successfully.</div>';['manualCustomer','manualItems','manualTotal','manualPaid','manualPhone','manualDueDate'].forEach(id=>document.getElementById(id).value='');currentPage=1;await loadHome();}catch(e){result.innerHTML=`<div class="status-error">${escapeHtml(e.message)}</div>`;}}
    let mediaRecorder=null,audioChunks=[],recording=false,voiceTimeout=null;
    window.startVoice=async function startVoice(){const btn=document.getElementById('voiceButton'),status=document.getElementById('voiceStatus');if(recording){stopRecording();return;}if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia){status.textContent='Your browser does not support microphone recording.';return;}try{const stream=await navigator.mediaDevices.getUserMedia({audio:true});audioChunks=[];let mt='';if(MediaRecorder.isTypeSupported('audio/webm;codecs=opus'))mt='audio/webm;codecs=opus';else if(MediaRecorder.isTypeSupported('audio/webm'))mt='audio/webm';mediaRecorder=mt?new MediaRecorder(stream,{mimeType:mt}):new MediaRecorder(stream);mediaRecorder.ondataavailable=e=>{if(e.data&&e.data.size>0)audioChunks.push(e.data)};mediaRecorder.onstop=async()=>{stream.getTracks().forEach(t=>t.stop());const blob=new Blob(audioChunks,{type:mt||'audio/webm'});if(blob.size<1000){status.textContent='No voice captured. Please speak clearly and try again.';return;}await uploadVoice(blob)};mediaRecorder.start(250);recording=true;btn.textContent='⏹️';btn.classList.add('recording');status.textContent='Listening... Speak now';voiceTimeout=setTimeout(()=>{if(recording)stopRecording()},10000);}catch(e){console.error(e);status.textContent='Microphone permission is required.';}}
    function stopRecording(){if(voiceTimeout)clearTimeout(voiceTimeout);if(mediaRecorder&&recording){recording=false;mediaRecorder.stop()}const b=document.getElementById('voiceButton');if(b){b.textContent='🎙️';b.classList.remove('recording')}}
    async function uploadVoice(blob){const status=document.getElementById('voiceStatus'),box=document.getElementById('voiceResult');status.textContent='Processing with AI...';try{const f=new FormData();f.append('file',blob,'voice.webm');const r=await fetch('/api/process_voice_note',{method:'POST',body:f});const text=await r.text();let d;try{d=JSON.parse(text)}catch{throw new Error(text||'Server returned invalid response.')}if(!r.ok||d.success===false)throw new Error(d.error||d.detail||'Voice processing failed.');const t=d.transaction||d;box.innerHTML=`<div class="card" style="text-align:left;"><div class="section-title">AI Transaction Preview</div><p><b>Customer:</b> ${escapeHtml(t.customer_name||t.customer||'-')}</p><p><b>Items:</b> ${formatItems(t.items,t.item)}</p><p><b>Total:</b> ₹${Number(t.total_amount||0).toLocaleString('en-IN')}</p><p><b>Paid:</b> ₹${Number(t.paid_amount||0).toLocaleString('en-IN')}</p><p><b>Outstanding:</b> ₹${Number(t.outstanding_amount||0).toLocaleString('en-IN')}</p><input id="voicePhone" class="input" style="margin-top:7px;" placeholder="Customer phone (optional)" type="tel"><button onclick='confirmVoiceTransaction(${JSON.stringify(t)})' class="primary-btn" style="margin-top:15px;">✓ Confirm & Save</button></div>`;status.textContent='AI understood your transaction';}catch(e){console.error(e);status.textContent='Voice processing failed';box.innerHTML=`<div class="card"><div class="status-error">${escapeHtml(e.message)}</div></div>`;}}
    function parseItemsClient(value){return value?String(value).split(/[,\n]+/).map(x=>x.trim()).filter(Boolean):[];}
    async function confirmVoiceTransaction(t){try{const pi=document.getElementById('voicePhone'),phone=pi?pi.value.trim():'';const r=await fetch('/api/transactions/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({customer:t.customer_name||t.customer||'',phone:phone||null,item:(Array.isArray(t.items)&&t.items.length?t.items[0]:(t.item||null)),items:(Array.isArray(t.items)?t.items:parseItemsClient(t.item)),transaction_type:t.intent||'sale',total_amount:Number(t.total_amount||0),paid_amount:Number(t.paid_amount||0),payment_method:t.payment_method||null,due_date:t.due_date||null,payment_status:t.payment_status||null,detected_language:t.language||t.detected_language||null,confidence:Number(t.confidence||0),raw_transcript:t.transcript||t.raw_transcript||null})});const d=await r.json();if(!r.ok||d.success===false)throw new Error(d.error||d.detail||'Could not save transaction.');document.getElementById('voiceStatus').textContent='Transaction saved ✓';document.getElementById('voiceResult').innerHTML='<div class="status-ok">✓ Transaction saved successfully.</div>';currentPage=1;await loadHome();}catch(e){document.getElementById('voiceStatus').textContent=e.message;}}
    function initializeHome(){
        if(!document.getElementById('transactionsBody')){
            setTimeout(initializeHome,100);
            return;
        }
        loadHome();
    }
    setTimeout(initializeHome,50);
    </script>"""


# ============================================================
# CUSTOMERS HTML
# ============================================================

def customers_html():
    return """
    <div class="app"><div class="container">__NAV__
        <h1>Customers</h1><div class="subtitle">Manage your customer list. Only one customer can be edited at a time.</div>
        <div style="margin-top:20px;"><button class="primary-btn" onclick="toggleAddCustomer()">+ Add Customer</button></div>
        <div id="addCustomerPanel" class="card" style="margin-top:16px;display:none;"><div class="section-title">Add Customer</div><div class="form-grid"><input id="newCustomerName" class="input" placeholder="Customer name"><input id="newCustomerPhone" class="input" placeholder="+91 9876543210" type="tel"></div><div class="checkbox-row"><input id="newReminderEnabled" type="checkbox"><label for="newReminderEnabled">Enable payment reminders</label></div><div class="checkbox-row"><input id="newReminderConsent" type="checkbox"><label for="newReminderConsent">Customer has given reminder consent</label></div><button class="primary-btn" style="margin-top:15px;" onclick="addCustomer()">Save Customer</button><div id="addCustomerResult" style="margin-top:12px;"></div></div>
        <div id="customersList" style="margin-top:24px;"></div><div id="editPanel" class="card" style="margin-top:18px;display:none;"></div>
    </div></div>
    <script>
    let customersData=[],editingCustomerId=null;
    function escapeHtml(v){return String(v).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;');}
    function toggleAddCustomer(){const p=document.getElementById('addCustomerPanel');p.style.display=p.style.display==='none'?'block':'none';}
    async function loadCustomers(){try{const r=await fetch('/api/customers');const d=await r.json();if(!d.success)throw new Error(d.error||'Could not load customers.');customersData=d.customers||[];renderCustomers();}catch(e){document.getElementById('customersList').innerHTML=`<div class="card status-error">${escapeHtml(e.message)}</div>`;}}
    function renderCustomers(){const b=document.getElementById('customersList');if(!customersData.length){b.innerHTML='<div class="card empty">No customers yet. Use + Add Customer to create one.</div>';return;}b.innerHTML=customersData.map(c=>`<div class="card customer-row"><div><div style="font-size:18px;font-weight:800;">${escapeHtml(c.name||'-')}</div><div class="customer-meta">${c.phone?'📱 '+escapeHtml(c.phone):'No phone'} · Outstanding: <b>₹${Number(c.outstanding_amount||0).toLocaleString('en-IN')}</b></div></div><div class="customer-actions"><button class="secondary-btn" onclick="openEdit(${c.id})">Update</button><button class="danger-btn" onclick="deleteCustomer(${c.id})">Delete</button></div></div>`).join('');}
    function openEdit(id){const c=customersData.find(x=>x.id===id);if(!c)return;editingCustomerId=id;const p=document.getElementById('editPanel');p.style.display='block';p.innerHTML=`<div class="section-title">Update Customer</div><div class="form-grid"><input id="editName" class="input" value="${escapeHtml(c.name||'')}" placeholder="Customer name"><input id="editPhone" class="input" value="${escapeHtml(c.phone||'')}" placeholder="Phone" type="tel"><select id="editLanguage" class="input"><option value="hindi">Hindi</option><option value="marathi">Marathi</option><option value="english">English</option></select><input id="editFrequency" class="input" type="number" min="1" value="${Number(c.reminder_frequency_days||3)}" placeholder="Reminder frequency (days)"></div><div class="checkbox-row"><input id="editReminderEnabled" type="checkbox" ${c.reminder_enabled?'checked':''}><label for="editReminderEnabled">Enable payment reminders</label></div><div class="checkbox-row"><input id="editReminderConsent" type="checkbox" ${c.reminder_consent?'checked':''}><label for="editReminderConsent">Customer has given reminder consent</label></div><div style="margin-top:15px;display:flex;gap:10px;"><button class="primary-btn" onclick="saveEdit()">Save Changes</button><button class="secondary-btn" onclick="closeEdit()">Cancel</button></div><div id="editResult" style="margin-top:12px;"></div>`;document.getElementById('editLanguage').value=c.preferred_reminder_language||'hindi';p.scrollIntoView({behavior:'smooth',block:'start'});}
    function closeEdit(){editingCustomerId=null;const p=document.getElementById('editPanel');p.style.display='none';p.innerHTML='';}
    async function saveEdit(){if(!editingCustomerId)return;const result=document.getElementById('editResult');try{const r=await fetch('/api/customers/'+editingCustomerId,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:document.getElementById('editName').value.trim(),phone:document.getElementById('editPhone').value.trim()||null,preferred_reminder_language:document.getElementById('editLanguage').value,reminder_enabled:document.getElementById('editReminderEnabled').checked,reminder_consent:document.getElementById('editReminderConsent').checked,reminder_frequency_days:Number(document.getElementById('editFrequency').value||3)})});const d=await r.json();if(!r.ok||d.success===false)throw new Error(d.error||d.detail||'Could not update customer.');await loadCustomers();closeEdit();}catch(e){result.innerHTML=`<div class="status-error">${escapeHtml(e.message)}</div>`;}}
    async function deleteCustomer(id){const c=customersData.find(x=>x.id===id);if(!c)return;if(!confirm(`Delete ${c.name}? Customers with active transactions cannot be deleted.`))return;try{const r=await fetch('/api/customers/'+id,{method:'DELETE'});const d=await r.json();if(!r.ok||d.success===false)throw new Error(d.error||d.detail||'Could not delete customer.');if(editingCustomerId===id)closeEdit();await loadCustomers();}catch(e){alert(e.message);}}
    async function addCustomer(){const result=document.getElementById('addCustomerResult'),name=document.getElementById('newCustomerName').value.trim(),phone=document.getElementById('newCustomerPhone').value.trim();if(!name){result.innerHTML='<div class="status-error">Customer name is required.</div>';return;}try{const r=await fetch('/api/customers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,phone:phone||null,reminder_enabled:document.getElementById('newReminderEnabled').checked,reminder_consent:document.getElementById('newReminderConsent').checked})});const d=await r.json();if(!r.ok||d.success===false)throw new Error(d.error||d.detail||'Could not create customer.');result.innerHTML='<div class="status-ok">✓ Customer saved.</div>';document.getElementById('newCustomerName').value='';document.getElementById('newCustomerPhone').value='';await loadCustomers();}catch(e){result.innerHTML=`<div class="status-error">${escapeHtml(e.message)}</div>`;}}
    loadCustomers();
    </script>"""


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
    """Render the page HTML and execute embedded page JavaScript reliably.

    NiceGUI can update page fragments dynamically. To avoid scripts being inserted
    as inert HTML, move every inline <script> block into the document head and
    keep only markup in the body fragment.
    """
    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, flags=re.IGNORECASE | re.DOTALL)
    body_html = re.sub(r"<script(?:\s[^>]*)?>.*?</script>", "", html, flags=re.IGNORECASE | re.DOTALL)

    ui.add_head_html(APP_CSS)
    ui.add_head_html(THEME_SCRIPT)
    for script in scripts:
        ui.add_head_html(f"<script>\n{script}\n</script>")

    ui.add_body_html(body_html)


@ui.page("/")
def home_page():

    setup_page(
        home_html().replace(
            "__NAV__",
            navigation_html(),
        )
    )


@ui.page("/dashboard")
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
