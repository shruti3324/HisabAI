"""
Cashfree payment integration for Voice Ledger.

Flow:

Create payment request
        ↓
Cashfree Sandbox
        ↓
Customer pays
        ↓
Cashfree webhook
        ↓
Signature verification
        ↓
Payment verified
        ↓
Ledger updated
"""

import os
import uuid
import hmac
import hashlib
import base64
from datetime import datetime

import requests
from sqlmodel import select

from db import get_session
from models import Payment
from services.transaction_service import create_transaction


# ============================================================
# CONFIG
# ============================================================

CASHFREE_BASE_URL = "https://sandbox.cashfree.com/pg"

CASHFREE_API_VERSION = os.getenv(
    "CASHFREE_API_VERSION",
    "2025-01-01",
)


def _credentials():
    client_id = os.getenv(
        "CASHFREE_CLIENT_ID"
    )

    client_secret = os.getenv(
        "CASHFREE_CLIENT_SECRET"
    )

    if not client_id or not client_secret:
        raise RuntimeError(
            "CASHFREE_CLIENT_ID / "
            "CASHFREE_CLIENT_SECRET "
            "are not configured."
        )

    return client_id, client_secret


# ============================================================
# CASHFREE HEADERS
# ============================================================

def _headers():
    client_id, client_secret = _credentials()

    return {
        "accept": "application/json",
        "content-type": "application/json",
        "x-api-version": CASHFREE_API_VERSION,
        "x-client-id": client_id,
        "x-client-secret": client_secret,
    }


# ============================================================
# CREATE PAYMENT REQUEST
# ============================================================

def create_payment_request(
    customer_id: int,
    amount: float,
    user_id: str = "demo",
):
    """
    Creates a Cashfree Sandbox order.

    Returns the Payment database record.

    The customer receives a Cashfree checkout/payment
    session through the returned payment_session_id.
    """

    amount = float(amount)

    if amount <= 0:
        raise ValueError(
            "Payment amount must be greater than zero."
        )

    with get_session() as session:

        # ----------------------------------------------------
        # FIND CUSTOMER
        # ----------------------------------------------------

        from models import Customer

        customer = session.get(
            Customer,
            customer_id,
        )

        if not customer or customer.user_id != user_id:
            raise ValueError(
                "Customer was not found."
            )

        # ----------------------------------------------------
        # CREATE UNIQUE ORDER ID
        # ----------------------------------------------------

        order_id = (
            f"hisab_{customer_id}_"
            f"{uuid.uuid4().hex[:16]}"
        )

        customer_name = (
            customer.name
            or "Customer"
        )

        customer_phone = (
            customer.phone
            or "9999999999"
        )

        # Cashfree requires a usable customer identifier.
        customer_id_for_cf = (
            f"customer_{customer.id}"
        )

        # ----------------------------------------------------
        # CASHFREE ORDER
        # ----------------------------------------------------

        payload = {
            "order_id": order_id,

            "order_amount": round(
                amount,
                2,
            ),

            "order_currency": "INR",

            "customer_details": {
                "customer_id":
                    customer_id_for_cf,

                "customer_name":
                    customer_name,

                "customer_phone":
                    customer_phone,
            },

            "order_meta": {
                "return_url":
                    "http://localhost:8080/"
            },

            "order_note":
                "Voice Ledger payment",
        }

        try:

            response = requests.post(
                f"{CASHFREE_BASE_URL}/orders",
                headers=_headers(),
                json=payload,
                timeout=30,
            )

        except requests.RequestException as exc:

            raise RuntimeError(
                f"Cashfree connection failed: {exc}"
            )

        if response.status_code >= 400:

            try:
                error_data = response.json()

            except Exception:
                error_data = response.text

            raise RuntimeError(
                "Cashfree order creation failed: "
                f"{error_data}"
            )

        try:

            data = response.json()

        except Exception:

            raise RuntimeError(
                "Cashfree returned an invalid response."
            )

        payment_session_id = data.get(
            "payment_session_id"
        )

        if not payment_session_id:

            raise RuntimeError(
                "Cashfree did not return "
                "payment_session_id."
            )

        # ----------------------------------------------------
        # SAVE OUR PAYMENT RECORD
        # ----------------------------------------------------

        payment = Payment(
            user_id=user_id,
            customer_id=customer_id,
            provider="cashfree",
            provider_reference=order_id,
            amount=amount,
            status="created",
            payment_link_url=None,
            provider_payment_id=None,
            provider_order_id=order_id,
        )

        # Store session ID if your model has this field.
        if hasattr(
            payment,
            "payment_session_id"
        ):
            payment.payment_session_id = (
                payment_session_id
            )

        session.add(payment)
        session.commit()
        session.refresh(payment)

        # Keep the session ID available to the UI.
        payment._cashfree_session_id = (
            payment_session_id
        )

        return payment


# ============================================================
# GET PAYMENT STATUS
# ============================================================

def get_cashfree_order(
    order_id: str,
):
    """
    Fetches the current Cashfree order.
    """

    try:

        response = requests.get(
            f"{CASHFREE_BASE_URL}/orders/{order_id}",
            headers=_headers(),
            timeout=30,
        )

    except requests.RequestException as exc:

        raise RuntimeError(
            f"Cashfree connection failed: {exc}"
        )

    if response.status_code >= 400:

        try:
            data = response.json()

        except Exception:
            data = response.text

        raise RuntimeError(
            f"Cashfree order lookup failed: {data}"
        )

    return response.json()


# ============================================================
# WEBHOOK SIGNATURE
# ============================================================

def verify_cashfree_webhook(
    raw_body: bytes,
    timestamp: str,
    received_signature: str,
) -> bool:

    secret = os.getenv(
        "CASHFREE_CLIENT_SECRET"
    )

    if not secret:
        raise RuntimeError(
            "CASHFREE_CLIENT_SECRET is not configured."
        )

    signed_payload = (
        timestamp.encode("utf-8")
        + raw_body
    )

    digest = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).digest()

    expected_signature = (
        base64.b64encode(digest)
        .decode("utf-8")
    )

    return hmac.compare_digest(
        expected_signature,
        received_signature,
    )


# ============================================================
# RECONCILE VERIFIED PAYMENT
# ============================================================

def reconcile_verified_payment(
    payment,
    provider_payment_id: str,
    provider_order_id: str | None = None,
    user_id: str = "demo",
):
    """
    Converts a verified Cashfree payment into
    a Voice Ledger payment transaction.

    Idempotent:
    the same Cashfree payment cannot be
    inserted twice.
    """

    if not provider_payment_id:
        raise ValueError(
            "Missing Cashfree payment ID."
        )

    with get_session() as session:

        existing = session.get(
            Payment,
            payment.id,
        )

        if not existing:
            raise ValueError(
                "Payment record was not found."
            )

        # ----------------------------------------------------
        # IDEMPOTENCY
        # ----------------------------------------------------

        if (
            existing.status
            in {
                "paid",
                "verified",
                "success",
            }
            and existing.provider_payment_id
            == provider_payment_id
        ):

            return existing

        # ----------------------------------------------------
        # MAKE SURE PAYMENT BELONGS TO CASHFREE
        # ----------------------------------------------------

        if existing.provider != "cashfree":

            raise ValueError(
                "Payment provider mismatch."
            )

        # ----------------------------------------------------
        # UPDATE PAYMENT
        # ----------------------------------------------------

        existing.provider_payment_id = (
            provider_payment_id
        )

        if provider_order_id:
            existing.provider_order_id = (
                provider_order_id
            )

        existing.status = "paid"

        session.add(existing)
        session.commit()

        # ----------------------------------------------------
        # CHECK WHETHER LEDGER TRANSACTION
        # ALREADY EXISTS
        # ----------------------------------------------------

        existing_transaction = session.exec(
            select(Transaction)
            .where(
                Transaction.user_id
                == user_id,

                Transaction.source
                == "cashfree",

                Transaction.external_reference
                == provider_payment_id,
            )
        ).first()

        if existing_transaction:

            session.refresh(existing)

            return existing

        # ----------------------------------------------------
        # CREATE VERIFIED PAYMENT TRANSACTION
        # ----------------------------------------------------

        transaction_payload = {

            "customer_id":
                existing.customer_id,

            "total_amount":
                float(existing.amount),

            "paid_amount":
                float(existing.amount),

            "transaction_type":
                "payment",

            "payment_method":
                "upi",

            "source":
                "cashfree",

            "external_reference":
                provider_payment_id,

            "user_id":
                user_id,
        }

        create_transaction(
            transaction_payload
        )

        session.refresh(existing)

        return existing


# ============================================================
# DEMO PAYMENT
# ============================================================

def simulate_demo_payment(
    customer_id: int,
    amount: float,
    user_id: str = "demo",
):
    """
    Optional offline hackathon fallback.

    Does NOT represent a real payment.
    """

    amount = float(amount)

    if amount <= 0:
        raise ValueError(
            "Payment amount must be greater than zero."
        )

    transaction = create_transaction(
        {
            "customer_id":
                customer_id,

            "total_amount":
                amount,

            "paid_amount":
                amount,

            "transaction_type":
                "payment",

            "payment_method":
                "upi",

            "source":
                "demo_gpay",

            "user_id":
                user_id,
        }
    )

    return transaction