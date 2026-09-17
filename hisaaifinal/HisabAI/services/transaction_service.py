"""The only service allowed to mutate the financial ledger."""
from datetime import datetime
from sqlmodel import select
from db import get_session
from models import Customer, Transaction
from services.customer_service import resolve_customer
from services.validation_service import validate_transaction


def _active_transactions(session, user_id: str, customer_id: int | None = None):
    statement = select(Transaction).where(Transaction.user_id == user_id, Transaction.status == "active")
    if customer_id is not None:
        statement = statement.where(Transaction.customer_id == customer_id)
    return session.exec(statement).all()


def balance_for_transactions(transactions: list[Transaction]) -> float:
    balance = 0.0
    for transaction in transactions:
        if transaction.transaction_type in {"sale", "credit_sale", "refund", "adjustment"}:
            balance += transaction.outstanding_amount
        elif transaction.transaction_type == "payment":
            balance -= transaction.paid_amount
    return round(max(0.0, balance), 2)


def create_transaction(payload: dict, user_id: str = "demo") -> Transaction:
    value = validate_transaction(payload)
    with get_session() as session:
        customer = resolve_customer(session, user_id=user_id, name=value.customer_name, phone=payload.get("phone"))
        if value.transaction_type == "payment":
            current = balance_for_transactions(_active_transactions(session, user_id, customer.id))
            if value.paid_amount > current + 0.009:
                raise ValueError(f"Payment is greater than {customer.name}'s outstanding balance of ₹{current:,.2f}.")
        transaction = Transaction(user_id=user_id, customer_id=customer.id, customer=customer.name,
            transaction_type=value.transaction_type, item=value.item, total_amount=value.total_amount,
            paid_amount=value.paid_amount, outstanding_amount=value.outstanding_amount,
            payment_method=value.payment_method, due_date=value.due_date,
            payment_status="credit" if value.outstanding_amount else "paid", detected_language=value.detected_language,
            confidence=value.confidence, confirmed=True, raw_transcript=payload.get("raw_transcript"),
            source=payload.get("source", "manual"))
        session.add(transaction)
        customer.updated_at = datetime.utcnow()
        session.add(customer)
        session.commit()
        session.refresh(transaction)
        return transaction


def reverse_transaction(transaction_id: int, user_id: str = "demo") -> Transaction:
    with get_session() as session:
        original = session.get(Transaction, transaction_id)
        if not original or original.user_id != user_id:
            raise ValueError("Transaction was not found.")
        if original.status == "reversed":
            raise ValueError("This transaction has already been reversed.")
        original.status = "reversed"
        original.updated_at = datetime.utcnow()
        reversal = Transaction(user_id=user_id, customer_id=original.customer_id, customer=original.customer,
            transaction_type="reversal", total_amount=0, paid_amount=0, outstanding_amount=0,
            confirmed=True, source="undo", status="active", reversal_of=original.id,
            raw_transcript=f"Reversal of transaction #{original.id}")
        session.add(original); session.add(reversal); session.commit(); session.refresh(reversal)
        return reversal


def customer_summary(customer: Customer, user_id: str = "demo") -> dict:
    with get_session() as session:
        txns = _active_transactions(session, user_id, customer.id)
    purchases = sum(t.total_amount for t in txns if t.transaction_type in {"sale", "credit_sale"})
    payments = sum(t.paid_amount for t in txns if t.transaction_type == "payment") + sum(t.paid_amount for t in txns if t.transaction_type in {"sale", "credit_sale"})
    unpaid = [t for t in txns if t.outstanding_amount > 0]
    return {"id": customer.id, "name": customer.name, "phone": customer.phone,
        "preferred_reminder_language": customer.preferred_reminder_language,
        "reminder_enabled": customer.reminder_enabled, "reminder_consent": customer.reminder_consent,
        "reminder_channel": customer.reminder_channel, "reminder_frequency_days": customer.reminder_frequency_days,
        "quiet_hours": customer.quiet_hours, "total_purchases": round(purchases, 2),
        "total_payments": round(payments, 2), "outstanding_amount": balance_for_transactions(txns),
        "transaction_count": len(txns), "last_transaction_date": max((t.created_at for t in txns), default=None),
        "oldest_unpaid_transaction": min((t.created_at for t in unpaid), default=None)}


def list_customer_summaries(user_id: str = "demo") -> list[dict]:
    with get_session() as session:
        customers = session.exec(select(Customer).where(Customer.user_id == user_id)).all()
    return sorted((customer_summary(c, user_id) for c in customers), key=lambda c: c["outstanding_amount"], reverse=True)


def get_customer_summary(customer_id: int, user_id: str = "demo") -> dict:
    """Return a single customer summary, without exposing another user's data."""
    with get_session() as session:
        customer = session.get(Customer, customer_id)
        if not customer or customer.user_id != user_id:
            raise ValueError("Customer was not found.")
    return customer_summary(customer, user_id)


def get_customer_ledger(customer_id: int, user_id: str = "demo") -> list[dict]:
    """Chronological active ledger entries with the balance after each entry."""
    with get_session() as session:
        customer = session.get(Customer, customer_id)
        if not customer or customer.user_id != user_id:
            raise ValueError("Customer was not found.")
        transactions = _active_transactions(session, user_id, customer_id)
    transactions.sort(key=lambda transaction: (transaction.created_at, transaction.id or 0))
    balance = 0.0
    entries = []
    for transaction in transactions:
        if transaction.transaction_type in {"sale", "credit_sale", "refund", "adjustment"}:
            balance += transaction.outstanding_amount
        elif transaction.transaction_type == "payment":
            balance -= transaction.paid_amount
        entries.append({
            "id": transaction.id,
            "created_at": transaction.created_at,
            "transaction_type": transaction.transaction_type,
            "item": transaction.item,
            "total_amount": transaction.total_amount,
            "paid_amount": transaction.paid_amount,
            "outstanding_amount": transaction.outstanding_amount,
            "balance_after": round(max(0.0, balance), 2),
        })
    return list(reversed(entries))
