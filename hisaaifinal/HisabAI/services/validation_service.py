"""Strict validation of untrusted AI and browser payloads."""
from dataclasses import dataclass
from datetime import date
from typing import Any


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedTransaction:
    customer_name: str
    transaction_type: str
    item: str | None
    total_amount: float
    paid_amount: float
    outstanding_amount: float
    due_date: date | None
    payment_method: str | None
    detected_language: str | None
    confidence: float


VALID_TYPES = {"sale", "credit_sale", "payment", "refund", "adjustment"}


def _number(value: Any, field: str) -> float:
    try:
        number = round(float(value), 2)
    except (TypeError, ValueError):
        raise ValidationError(f"Couldn't understand the {field}.")
    if number < 0:
        raise ValidationError(f"{field.replace('_', ' ').capitalize()} cannot be negative.")
    return number


def validate_transaction(payload: dict[str, Any]) -> ValidatedTransaction:
    name = str(payload.get("customer_name") or payload.get("customer") or "").strip()
    if not name:
        raise ValidationError("Please add a customer before saving.")
    txn_type = str(payload.get("transaction_type") or "").lower()
    if txn_type not in VALID_TYPES:
        raise ValidationError("Please choose whether this is a sale, credit sale, or payment.")
    total = _number(payload.get("total_amount"), "total amount")
    paid = _number(payload.get("paid_amount", 0), "paid amount")
    if txn_type == "payment":
        if total <= 0:
            raise ValidationError("A payment must be greater than ₹0.")
        paid = total
    elif paid > total:
        raise ValidationError("Paid amount cannot be more than total amount.")
    expected = round(total - paid, 2)
    supplied = payload.get("outstanding_amount")
    if supplied not in (None, "") and abs(_number(supplied, "outstanding amount") - expected) > 0.009:
        raise ValidationError("Outstanding must equal total amount minus paid amount.")
    if txn_type == "sale" and expected > 0:
        txn_type = "credit_sale"
    if txn_type == "credit_sale" and expected == 0:
        txn_type = "sale"
    due = payload.get("due_date")
    if isinstance(due, str) and due:
        try:
            due = date.fromisoformat(due)
        except ValueError:
            raise ValidationError("Due date must be a valid date.")
    return ValidatedTransaction(name, txn_type, str(payload.get("item") or "").strip() or None,
        total, paid, expected, due if isinstance(due, date) else None,
        payload.get("payment_method"), payload.get("detected_language"),
        max(0.0, min(1.0, float(payload.get("confidence", 0) or 0))))
