"""Safe, database-backed business metrics."""
from datetime import datetime, timedelta, timezone
from sqlmodel import select
from db import get_session
from models import Transaction
from services.transaction_service import balance_for_transactions, list_customer_summaries


def _transactions(user_id="demo"):
    with get_session() as session:
        return session.exec(select(Transaction).where(Transaction.user_id == user_id, Transaction.status == "active")).all()


def dashboard_summary(user_id="demo") -> dict:
    txns = _transactions(user_id); today = datetime.now(timezone.utc).date()
    today_txns = [t for t in txns if t.created_at.date() == today]
    return {"today_sales": round(sum(t.total_amount for t in today_txns if t.transaction_type in {"sale", "credit_sale"}), 2),
      "received_today": round(sum(t.paid_amount for t in today_txns if t.transaction_type == "payment") + sum(t.paid_amount for t in today_txns if t.transaction_type in {"sale", "credit_sale"}), 2),
      "new_credit_today": round(sum(t.outstanding_amount for t in today_txns if t.transaction_type in {"sale", "credit_sale"}), 2),
      "outstanding_udhaar": balance_for_transactions(txns), "transaction_count": len(today_txns),
      "customer_count": len(list_customer_summaries(user_id))}


def top_debtors(user_id="demo", minimum=0.0) -> list[dict]:
    return [c for c in list_customer_summaries(user_id) if c["outstanding_amount"] > minimum]


def customer_transactions(customer_id: int, user_id="demo") -> list[Transaction]:
    return [t for t in _transactions(user_id) if t.customer_id == customer_id]


def overdue_customers(days: int = 0, user_id="demo") -> list[dict]:
    threshold = datetime.now(timezone.utc).date() - timedelta(days=days)
    output = []
    for customer in list_customer_summaries(user_id):
        oldest = customer["oldest_unpaid_transaction"]
        if customer["outstanding_amount"] > 0 and oldest and oldest.date() <= threshold:
            output.append(customer)
    return output
