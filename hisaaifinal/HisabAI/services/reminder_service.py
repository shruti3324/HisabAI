"""AI-powered consent-aware reminder and real Twilio voice collection."""

import json
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

# Always load the project's .env file
BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

ENV_FILE = os.path.join(
    BASE_DIR,
    ".env",
)

load_dotenv(
    ENV_FILE,
    override=True,
)

print(
    "[REMINDER ENV] .env:",
    ENV_FILE,
)

print(
    "[REMINDER ENV] Twilio SID loaded:",
    bool(os.getenv("TWILIO_ACCOUNT_SID")),
)

print(
    "[REMINDER ENV] Twilio auth loaded:",
    bool(os.getenv("TWILIO_AUTH_TOKEN")),
)

print(
    "[REMINDER ENV] Twilio phone loaded:",
    bool(os.getenv("TWILIO_PHONE_NUMBER")),
)

print(
    "[REMINDER ENV] Public URL loaded:",
    bool(os.getenv("PUBLIC_BASE_URL")),
)
from sqlmodel import select

from db import get_session
from models import Customer, Reminder

from services.risk_service import reminder_priority

from services.transaction_service import (
    get_customer_summary,
    list_customer_summaries,
)


# =========================================================
# PROVIDER
# =========================================================

class ReminderProvider:
    name = "provider"

    def send(
        self,
        *,
        customer: Customer,
        message: str,
        reminder_id: int | None = None,
    ) -> dict:
        raise NotImplementedError


class TwilioVoiceProvider(ReminderProvider):
    name = "voice_call"

    def __init__(self):
        try:
            from twilio.rest import Client
        except ImportError:
            raise RuntimeError(
                "Twilio is not installed. Run: pip install twilio"
            )

        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_PHONE_NUMBER")
        public_base_url = os.getenv("PUBLIC_BASE_URL")

        if not account_sid:
            raise RuntimeError(
                "TWILIO_ACCOUNT_SID is not configured."
            )

        if not auth_token:
            raise RuntimeError(
                "TWILIO_AUTH_TOKEN is not configured."
            )

        if not from_number:
            raise RuntimeError(
                "TWILIO_PHONE_NUMBER is not configured."
            )

        if not public_base_url:
            raise RuntimeError(
                "PUBLIC_BASE_URL is not configured."
            )

        self.client = Client(
            account_sid,
            auth_token,
        )

        self.from_number = from_number
        self.public_base_url = public_base_url.rstrip("/")

    def send(
        self,
        *,
        customer: Customer,
        message: str,
        reminder_id: int | None = None,
    ) -> dict:

        if not customer.phone:
            raise ValueError(
                "Customer does not have a phone number."
            )

        if not reminder_id:
            raise ValueError(
                "Reminder ID is required for voice calls."
            )

        phone = customer.phone.strip()

        if not phone.startswith("+"):
            raise ValueError(
                "Customer phone number must use international format, "
                "e.g. +919876543210."
            )

        voice_url = (
            f"{self.public_base_url}"
            f"/api/reminders/voice/{reminder_id}"
        )

        status_callback = (
            f"{self.public_base_url}"
            f"/api/reminders/voice-status"
        )

        call = self.client.calls.create(
            to=phone,
            from_=self.from_number,
            url=voice_url,
            method="POST",
            status_callback=status_callback,
            status_callback_method="POST",
        )

        return {
            "status": "queued",
            "outcome": "AI voice reminder call initiated.",
            "provider_message_id": None,
            "provider_call_id": call.sid,
        }


# =========================================================
# MESSAGE
# =========================================================

def _message(
    customer: Customer,
    summary: dict,
    priority: dict,
) -> str:

    language = (
        customer.preferred_reminder_language
        or "Hindi"
    )

    outstanding = float(
        summary.get("outstanding_amount") or 0
    )

    amount = f"₹{outstanding:,.0f}"

    days = priority.get("days_overdue") or 0

    if language == "Marathi":
        return (
            f"Namaskar {customer.name}. "
            f"Tumche {amount} payment pending aahe. "
            f"Tumhi payment kadhi karu shakta te sanga. "
            f"Dhanyavaad."
        )

    if language == "English":
        return (
            f"Hello {customer.name}. "
            f"Your payment of {amount} is pending. "
            f"Please tell me when you can make the payment. "
            f"Thank you."
        )

    suffix = (
        f" aur {days} din se due hai"
        if days
        else ""
    )

    return (
        f"Namaste {customer.name} ji. "
        f"Aapka {amount} ka payment pending hai"
        f"{suffix}. "
        f"Aap kab tak payment karenge, "
        f"kripya bata dijiye. Dhanyavaad."
    )


# =========================================================
# QUIET HOURS
# =========================================================

def _is_quiet_hours(
    customer: Customer,
) -> bool:

    if not customer.quiet_hours:
        return False

    try:
        value = customer.quiet_hours.strip()

        if "-" not in value:
            return False

        start_text, end_text = [
            part.strip()
            for part in value.split("-", 1)
        ]

        start_hour, start_minute = map(
            int,
            start_text.split(":"),
        )

        end_hour, end_minute = map(
            int,
            end_text.split(":"),
        )

        now = datetime.utcnow()

        current_minutes = (
            now.hour * 60
            + now.minute
        )

        start_minutes = (
            start_hour * 60
            + start_minute
        )

        end_minutes = (
            end_hour * 60
            + end_minute
        )

        if start_minutes < end_minutes:
            return (
                start_minutes
                <= current_minutes
                < end_minutes
            )

        return (
            current_minutes >= start_minutes
            or current_minutes < end_minutes
        )

    except Exception:
        return False


# =========================================================
# CUSTOMER REMINDER SETTINGS
# =========================================================

def update_reminder_settings(
    customer_id: int,
    payload: dict,
    user_id: str = "demo",
) -> Customer:

    with get_session() as session:

        customer = session.get(
            Customer,
            customer_id,
        )

        if (
            not customer
            or customer.user_id != user_id
        ):
            raise ValueError(
                "Customer was not found."
            )

        customer.phone = (
            (payload.get("phone") or "").strip()
            or None
        )

        customer.preferred_reminder_language = (
            payload.get("preferred_language")
            or "Hindi"
        )

        customer.reminder_enabled = bool(
            payload.get("reminder_enabled")
        )

        customer.reminder_consent = bool(
            payload.get("reminder_consent")
        )

        customer.reminder_channel = "voice_call"

        customer.reminder_frequency_days = max(
            1,
            int(
                payload.get(
                    "reminder_frequency_days"
                )
                or 3
            ),
        )

        customer.quiet_hours = (
            (payload.get("quiet_hours") or "").strip()
            or None
        )

        customer.updated_at = datetime.utcnow()

        session.add(customer)
        session.commit()
        session.refresh(customer)

        return customer


# =========================================================
# REMINDER CANDIDATES
# =========================================================

def reminder_candidates(
    user_id: str = "demo",
) -> list[dict]:

    ranked = []

    for summary in list_customer_summaries(
        user_id
    ):

        outstanding = float(
            summary.get("outstanding_amount")
            or 0
        )

        if outstanding <= 0:
            continue

        priority = reminder_priority(
            summary
        )

        ranked.append(
            {
                **summary,
                "priority": priority,
            }
        )

    order = {
        "HIGH ATTENTION": 0,
        "MEDIUM ATTENTION": 1,
        "LOW ATTENTION": 2,
    }

    return sorted(
        ranked,
        key=lambda row: (
            order.get(
                row["priority"]["level"],
                99,
            ),
            -float(
                row["outstanding_amount"]
            ),
        ),
    )


# =========================================================
# PROVIDER
# =========================================================

def _get_provider() -> ReminderProvider:
    return TwilioVoiceProvider()


# =========================================================
# VALIDATE CUSTOMER
# =========================================================

def _validate_reminder_customer(
    customer_id: int,
    user_id: str = "demo",
) -> tuple[Customer, dict, dict, str]:

    with get_session() as session:

        customer = session.get(
            Customer,
            customer_id,
        )

        if (
            not customer
            or customer.user_id != user_id
        ):
            raise ValueError(
                "Customer was not found."
            )

        if not customer.reminder_enabled:
            raise ValueError(
                "Reminders are disabled for this customer."
            )

        if not customer.reminder_consent:
            raise ValueError(
                "Customer consent is required before calling this customer."
            )

        if not customer.phone:
            raise ValueError(
                "Customer phone number is required for a voice reminder."
            )

        if not customer.phone.startswith("+"):
            raise ValueError(
                "Customer phone number must use international format, "
                "e.g. +919876543210."
            )

        summary = get_customer_summary(
            customer_id,
            user_id,
        )

        outstanding = float(
            summary.get("outstanding_amount")
            or 0
        )

        if outstanding <= 0:
            raise ValueError(
                "No reminder needed. "
                "This customer has no outstanding balance."
            )

        if _is_quiet_hours(customer):
            raise ValueError(
                "Reminder blocked because it is within "
                "the customer's quiet hours."
            )

        if customer.promise_to_pay_date:

            today = datetime.utcnow().date()

            if customer.promise_to_pay_date > today:
                raise ValueError(
                    "Reminder postponed because the customer "
                    "has an active promise-to-pay date."
                )

        priority = reminder_priority(
            summary
        )

        message = _message(
            customer,
            summary,
            priority,
        )

        return (
            customer,
            summary,
            priority,
            message,
        )


# =========================================================
# IMMEDIATE REMINDER
# =========================================================

def send_reminder(
    customer_id: int,
    user_id: str = "demo",
    force: bool = False,
) -> Reminder:

    """
    Send a real AI-powered voice reminder.

    force=False:
        Frequency protection is enabled.

    force=True:
        Frequency protection is bypassed.

    Even force=True still checks:
        - reminder enabled
        - consent
        - phone
        - outstanding balance
        - quiet hours
        - promise-to-pay
    """

    (
        customer,
        summary,
        priority,
        message,
    ) = _validate_reminder_customer(
        customer_id,
        user_id,
    )

    with get_session() as session:

        customer_db = session.get(
            Customer,
            customer_id,
        )

        if not customer_db:
            raise ValueError(
                "Customer was not found."
            )

        latest = session.exec(
            select(Reminder)
            .where(
                Reminder.user_id == user_id,
                Reminder.customer_id == customer_id,
                Reminder.status != "failed",
            )
            .order_by(
                Reminder.created_at.desc()
            )
        ).first()

        frequency_days = max(
            1,
            customer_db.reminder_frequency_days
            or 3,
        )

        if latest and not force:

            if latest.created_at >= (
                datetime.utcnow()
                - timedelta(days=frequency_days)
            ):
                raise ValueError(
                    f"A reminder was already logged "
                    f"within the selected "
                    f"{frequency_days}-day frequency."
                )

        outstanding = float(
            summary.get("outstanding_amount")
            or 0
        )

        ai_decision = (
            f"{priority['level']}: "
            f"{priority['recommended_action']}"
        )

        now = datetime.utcnow()

        reminder = Reminder(
            user_id=user_id,
            customer_id=customer_id,
            amount_at_reminder=outstanding,
            reminder_type="payment_reminder",
            channel="voice_call",
            status="queued",
            message=message,
            ai_decision=ai_decision,
            attempt_number=(
                customer_db.reminder_count or 0
            ) + 1,
            scheduled_at=now,
            promise_to_pay_date=(
                customer_db.promise_to_pay_date
            ),
        )

        session.add(reminder)
        session.commit()
        session.refresh(reminder)

        reminder_id = reminder.id

    try:

        with get_session() as session:

            customer_for_provider = session.get(
                Customer,
                customer_id,
            )

            if not customer_for_provider:
                raise ValueError(
                    "Customer was not found."
                )

            provider = _get_provider()

            response = provider.send(
                customer=customer_for_provider,
                message=message,
                reminder_id=reminder_id,
            )

    except Exception as exc:

        with get_session() as session:

            failed_reminder = session.get(
                Reminder,
                reminder_id,
            )

            if failed_reminder:

                failed_reminder.status = "failed"

                failed_reminder.outcome = (
                    f"Voice call failed: {exc}"
                )

                session.add(
                    failed_reminder
                )

                session.commit()

        raise

    with get_session() as session:

        db_reminder = session.get(
            Reminder,
            reminder_id,
        )

        if not db_reminder:
            raise ValueError(
                "Reminder record was not found."
            )

        db_reminder.status = (
            response.get(
                "status",
                "queued",
            )
        )

        db_reminder.outcome = response.get(
            "outcome"
        )

        db_reminder.provider_message_id = (
            response.get(
                "provider_message_id"
            )
        )

        db_reminder.provider_call_id = (
            response.get(
                "provider_call_id"
            )
        )

        if db_reminder.status in (
            "sent",
            "queued",
        ):
            db_reminder.sent_at = (
                datetime.utcnow()
            )

        customer_db = session.get(
            Customer,
            customer_id,
        )

        if customer_db:

            customer_db.last_reminder_at = (
                datetime.utcnow()
            )

            customer_db.reminder_count = (
                customer_db.reminder_count or 0
            ) + 1

            customer_db.updated_at = (
                datetime.utcnow()
            )

            session.add(customer_db)

        session.add(db_reminder)
        session.commit()
        session.refresh(db_reminder)

        return db_reminder


# =========================================================
# SCHEDULE REMINDER
# =========================================================

def schedule_reminder(
    customer_id: int,
    scheduled_at: datetime,
    user_id: str = "demo",
) -> Reminder:

    """
    Create ONE future scheduled Reminder.

    No Twilio call is made here.
    """

    now = datetime.utcnow()

    if scheduled_at.tzinfo is not None:

        scheduled_at = (
            scheduled_at.astimezone()
            .replace(tzinfo=None)
        )

    if scheduled_at <= now:
        raise ValueError(
            "Scheduled time must be in the future."
        )

    (
        customer,
        summary,
        priority,
        message,
    ) = _validate_reminder_customer(
        customer_id,
        user_id,
    )

    with get_session() as session:

        existing = session.exec(
            select(Reminder)
            .where(
                Reminder.user_id == user_id,
                Reminder.customer_id == customer_id,
                Reminder.status == "scheduled",
            )
            .order_by(
                Reminder.scheduled_at.asc()
            )
        ).first()

        if existing:
            raise ValueError(
                "This customer already has a scheduled reminder."
            )

        outstanding = float(
            summary.get("outstanding_amount")
            or 0
        )

        ai_decision = (
            f"{priority['level']}: "
            f"{priority['recommended_action']}"
        )

        reminder = Reminder(
            user_id=user_id,
            customer_id=customer_id,
            amount_at_reminder=outstanding,
            reminder_type="payment_reminder",
            channel="voice_call",
            status="scheduled",
            message=message,
            ai_decision=ai_decision,
            attempt_number=(
                customer.reminder_count or 0
            ) + 1,
            scheduled_at=scheduled_at,
            promise_to_pay_date=(
                customer.promise_to_pay_date
            ),
        )

        session.add(reminder)
        session.commit()
        session.refresh(reminder)

        return reminder


# =========================================================
# EXECUTE SCHEDULED REMINDER
# =========================================================

def execute_scheduled_reminder(
    reminder_id: int,
) -> Reminder:

    """
    Execute the EXISTING scheduled Reminder.

    IMPORTANT:
    This function never creates a second Reminder.
    """

    with get_session() as session:

        reminder = session.get(
            Reminder,
            reminder_id,
        )

        if not reminder:
            raise ValueError(
                "Scheduled reminder was not found."
            )

        if reminder.status not in {
            "scheduled",
            "queued",
        }:
            raise ValueError(
                f"Reminder #{reminder_id} cannot be executed "
                f"because its status is '{reminder.status}'."
            )

        customer = session.get(
            Customer,
            reminder.customer_id,
        )

        if not customer:
            reminder.status = "failed"
            reminder.outcome = (
                "Customer was not found."
            )

            session.add(reminder)
            session.commit()

            raise ValueError(
                "Customer was not found."
            )

        user_id = reminder.user_id
        customer_id = reminder.customer_id

    # Revalidate current customer settings.
    try:

        (
            customer,
            summary,
            priority,
            message,
        ) = _validate_reminder_customer(
            customer_id,
            user_id,
        )

    except Exception as exc:

        with get_session() as session:

            blocked = session.get(
                Reminder,
                reminder_id,
            )

            if blocked:

                blocked.status = "blocked"

                blocked.outcome = (
                    f"Scheduled reminder blocked: {exc}"
                )

                session.add(blocked)
                session.commit()
                session.refresh(blocked)

                return blocked

        raise

    outstanding = float(
        summary.get("outstanding_amount")
        or 0
    )

    ai_decision = (
        f"{priority['level']}: "
        f"{priority['recommended_action']}"
    )

    # Update the SAME reminder before sending.
    with get_session() as session:

        reminder = session.get(
            Reminder,
            reminder_id,
        )

        if not reminder:
            raise ValueError(
                "Reminder record was not found."
            )

        reminder.status = "queued"
        reminder.amount_at_reminder = outstanding
        reminder.message = message
        reminder.ai_decision = ai_decision
        reminder.promise_to_pay_date = (
            customer.promise_to_pay_date
        )

        session.add(reminder)
        session.commit()

    # Send using the SAME reminder ID.
    try:

        provider = _get_provider()

        response = provider.send(
            customer=customer,
            message=message,
            reminder_id=reminder_id,
        )

    except Exception as exc:

        with get_session() as session:

            reminder = session.get(
                Reminder,
                reminder_id,
            )

            if reminder:

                reminder.status = "failed"

                reminder.outcome = (
                    f"Voice call failed: {exc}"
                )

                session.add(reminder)
                session.commit()
                session.refresh(reminder)

        raise

    # Update SAME reminder after provider response.
    with get_session() as session:

        reminder = session.get(
            Reminder,
            reminder_id,
        )

        if not reminder:
            raise ValueError(
                "Reminder record was not found."
            )

        reminder.status = response.get(
            "status",
            "queued",
        )

        reminder.outcome = response.get(
            "outcome"
        )

        reminder.provider_message_id = (
            response.get(
                "provider_message_id"
            )
        )

        reminder.provider_call_id = (
            response.get(
                "provider_call_id"
            )
        )

        if reminder.status in {
            "sent",
            "queued",
        }:
            reminder.sent_at = (
                datetime.utcnow()
            )

        customer_db = session.get(
            Customer,
            customer_id,
        )

        if customer_db:

            customer_db.last_reminder_at = (
                datetime.utcnow()
            )

            customer_db.reminder_count = (
                customer_db.reminder_count or 0
            ) + 1

            customer_db.updated_at = (
                datetime.utcnow()
            )

            session.add(customer_db)

        session.add(reminder)
        session.commit()
        session.refresh(reminder)

        return reminder


# =========================================================
# DEMO COMPATIBILITY
# =========================================================

def send_demo_reminder(
    customer_id: int,
    user_id: str = "demo",
    force: bool = False,
) -> Reminder:

    return send_reminder(
        customer_id,
        user_id,
        force=force,
    )


# =========================================================
# VOICE TWIML
# =========================================================

def build_voice_twiml(
    reminder: Reminder,
) -> str:

    from xml.sax.saxutils import escape

    message = escape(
        reminder.message
    )

    language = "hi-IN"

    if reminder.message.startswith(
        "Hello"
    ):
        language = "en-IN"

    public_base_url = os.getenv(
        "PUBLIC_BASE_URL",
        "",
    ).rstrip("/")

    if not public_base_url:
        raise RuntimeError(
            "PUBLIC_BASE_URL is not configured."
        )

    action_url = (
        f"{public_base_url}"
        f"/api/reminders/voice-response/"
        f"{reminder.id}"
    )

    fallback_url = action_url

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather
        input="speech"
        action="{escape(action_url)}"
        method="POST"
        speechTimeout="auto"
        language="{language}"
        actionOnEmptyResult="true"
    >
        <Say
            language="{language}"
            voice="alice"
        >
            {message}
        </Say>
    </Gather>

    <Say
        language="{language}"
        voice="alice"
    >
        Dhanyavaad. Aapka din shubh ho.
    </Say>

    <Redirect method="POST">
        {escape(fallback_url)}
    </Redirect>
</Response>
"""


# =========================================================
# AI VOICE RESPONSE CLASSIFICATION
# =========================================================

def _classify_voice_response(
    speech: str,
    reminder: Reminder,
) -> dict:

    api_key = os.getenv(
        "GROQ_API_KEY"
    )

    if not api_key:

        return {
            "intent": "OTHER",
            "promise_days": None,
            "summary": (
                f"Customer response: {speech}"
            ),
        }

    try:

        from groq import Groq

        client = Groq(
            api_key=api_key
        )

        today = datetime.utcnow().date()

        prompt = f"""
You classify responses to a payment reminder call.

Today is {today.isoformat()}.

Customer response:
{speech}

Classify the response into exactly one:

PAID
PROMISE_TO_PAY
REFUSES
CALL_LATER
OTHER

Rules:

PAID examples:
"paid"
"payment kar diya"
"bhar diya"
"done"
"already paid"
"maine de diya"
"payment ho gaya"
"paise de diye"

PROMISE_TO_PAY examples:
"kal de dunga"
"kal payment karunga"
"tomorrow"
"udya denar"
"next week"
"shaam ko de dunga"
"parso de dunga"
"agle hafte de dunga"

CALL_LATER examples:
"baad mein call karo"
"call later"
"abhi busy hu"
"later call karna"
"thodi der baad phone karna"

REFUSES examples:
"nahi dunga"
"can't pay"
"won't pay"
"payment nahi karunga"

OTHER if unclear.

For PROMISE_TO_PAY estimate days:

kal/tomorrow = 1
day after tomorrow/parso = 2
next week = 7
next month = 30

Return ONLY valid JSON:

{{
    "intent": "PAID",
    "promise_days": null,
    "summary": "Customer says payment is already made."
}}
"""

        completion = client.chat.completions.create(
            model=os.getenv(
                "GROQ_REMINDER_MODEL",
                "llama-3.1-8b-instant",
            ),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict JSON classifier "
                        "for multilingual payment reminders. "
                        "Understand Hindi, Hinglish, "
                        "Marathi and English."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0,
            max_tokens=200,
        )

        content = (
            completion
            .choices[0]
            .message
            .content
            .strip()
        )

        content = (
            content
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        result = json.loads(
            content
        )

        intent = str(
            result.get(
                "intent",
                "OTHER",
            )
        ).upper()

        allowed_intents = {
            "PAID",
            "PROMISE_TO_PAY",
            "REFUSES",
            "CALL_LATER",
            "OTHER",
        }

        if intent not in allowed_intents:
            intent = "OTHER"

        promise_days = result.get(
            "promise_days"
        )

        if promise_days is not None:

            try:
                promise_days = max(
                    1,
                    int(promise_days),
                )
            except Exception:
                promise_days = None

        summary = (
            result.get("summary")
            or f"Customer response: {speech}"
        )

        return {
            "intent": intent,
            "promise_days": promise_days,
            "summary": summary,
        }

    except Exception as exc:

        print(
            "Groq reminder classification failed:",
            exc,
        )

        return {
            "intent": "OTHER",
            "promise_days": None,
            "summary": (
                f"Customer response: {speech}"
            ),
        }


# =========================================================
# PROCESS VOICE RESPONSE
# =========================================================

def process_voice_response(
    reminder_id: int,
    speech_result: str | None,
) -> Reminder:

    speech = (
        speech_result or ""
    ).strip()

    with get_session() as session:

        reminder = session.get(
            Reminder,
            reminder_id,
        )

        if not reminder:
            raise ValueError(
                "Reminder was not found."
            )

        if not speech:

            reminder.status = "answered"

            reminder.outcome = (
                "Customer answered but no "
                "speech was detected."
            )

            session.add(reminder)
            session.commit()
            session.refresh(reminder)

            return reminder

        classification = (
            _classify_voice_response(
                speech,
                reminder,
            )
        )

        intent = classification[
            "intent"
        ]

        promise_days = classification[
            "promise_days"
        ]

        summary = classification[
            "summary"
        ]

        if intent == "PAID":

            reminder.status = "answered"

            reminder.outcome = (
                "AI detected that the customer "
                "says the payment is already made. "
                f"{summary}"
            )

        elif intent == "PROMISE_TO_PAY":

            reminder.status = "promised"

            if promise_days:

                promise_date = (
                    datetime.utcnow().date()
                    + timedelta(
                        days=promise_days
                    )
                )

                reminder.promise_to_pay_date = (
                    promise_date
                )

                customer = session.get(
                    Customer,
                    reminder.customer_id,
                )

                if customer:

                    customer.promise_to_pay_date = (
                        promise_date
                    )

                    customer.updated_at = (
                        datetime.utcnow()
                    )

                    session.add(customer)

                reminder.outcome = (
                    "Customer promised to pay on "
                    f"{promise_date.isoformat()}. "
                    f"{summary}"
                )

            else:

                reminder.outcome = (
                    "Customer promised to pay. "
                    f"{summary}"
                )

        elif intent == "CALL_LATER":

            reminder.status = "answered"

            reminder.outcome = (
                "Customer requested a later call. "
                f"{summary}"
            )

        elif intent == "REFUSES":

            reminder.status = "answered"

            reminder.outcome = (
                "Customer declined the payment request. "
                f"{summary}"
            )

        else:

            reminder.status = "answered"

            reminder.outcome = (
                f"Customer response: {speech}"
            )

        session.add(reminder)
        session.commit()
        session.refresh(reminder)

        return reminder


# =========================================================
# TWILIO STATUS
# =========================================================

def update_voice_status(
    *,
    call_sid: str,
    call_status: str,
) -> Reminder | None:

    with get_session() as session:

        reminder = session.exec(
            select(Reminder)
            .where(
                Reminder.provider_call_id
                == call_sid
            )
        ).first()

        if not reminder:
            return None

        status_map = {
            "queued": "queued",
            "initiated": "queued",
            "ringing": "queued",
            "in-progress": "sent",
            "answered": "answered",
            "completed": "sent",
            "busy": "failed",
            "failed": "failed",
            "no-answer": "failed",
            "canceled": "failed",
        }

        new_status = status_map.get(
            call_status,
            reminder.status,
        )

        if reminder.status not in {
            "promised",
            "answered",
        }:

            reminder.status = new_status

        if call_status == "completed":

            if not reminder.outcome:

                reminder.outcome = (
                    "Voice call completed."
                )

        elif call_status == "no-answer":

            reminder.status = "failed"

            reminder.outcome = (
                "Customer did not answer the call."
            )

        elif call_status == "busy":

            reminder.status = "failed"

            reminder.outcome = (
                "Customer line was busy."
            )

        elif call_status == "failed":

            reminder.status = "failed"

            reminder.outcome = (
                "Voice call failed."
            )

        elif call_status == "canceled":

            reminder.status = "failed"

            reminder.outcome = (
                "Voice call was canceled."
            )

        session.add(reminder)
        session.commit()
        session.refresh(reminder)

        return reminder


# =========================================================
# REMINDER HISTORY
# =========================================================

def list_reminder_history(
    customer_id: int,
    user_id: str = "demo",
) -> list[Reminder]:

    with get_session() as session:

        return session.exec(
            select(Reminder)
            .where(
                Reminder.user_id == user_id,
                Reminder.customer_id == customer_id,
            )
            .order_by(
                Reminder.created_at.desc()
            )
        ).all()