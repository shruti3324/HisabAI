"""Customer resolution; avoids silently creating duplicate people."""
import re
from datetime import datetime
from sqlmodel import Session, select
from models import Customer


class AmbiguousCustomerError(ValueError):
    def __init__(self, customers: list[Customer]):
        super().__init__("More than one customer matches this name.")
        self.customers = customers


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).casefold()


def resolve_customer(session: Session, *, user_id: str, name: str, phone: str | None = None) -> Customer:
    normalized = normalize_name(name)
    matches = session.exec(select(Customer).where(Customer.user_id == user_id, Customer.normalized_name == normalized)).all()
    if phone:
        exact_phone = [c for c in matches if c.phone == phone]
        if len(exact_phone) == 1:
            return exact_phone[0]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise AmbiguousCustomerError(matches)
    customer = Customer(user_id=user_id, name=name.strip(), normalized_name=normalized, phone=phone)
    session.add(customer)
    session.flush()
    return customer


def customer_matches(session: Session, user_id: str, term: str) -> list[Customer]:
    term = normalize_name(term)
    return session.exec(select(Customer).where(Customer.user_id == user_id, Customer.normalized_name.contains(term))).all()
