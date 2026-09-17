"""Explainable reminder-priority indicator; not a credit or financial score."""
from datetime import datetime, timezone


def reminder_priority(customer: dict) -> dict:
    outstanding = float(customer.get("outstanding_amount") or 0)
    oldest = customer.get("oldest_unpaid_transaction")
    if not outstanding:
        return {"level": "LOW ATTENTION", "days_overdue": 0,
                "reasons": ["No outstanding balance."], "recommended_action": "No reminder needed."}
    days = 0
    if oldest:
        reference = oldest.replace(tzinfo=timezone.utc) if oldest.tzinfo is None else oldest
        days = max(0, (datetime.now(timezone.utc).date() - reference.date()).days)
    reasons = [f"₹{outstanding:,.0f} is currently outstanding."]
    if days:
        reasons.append(f"The oldest unpaid transaction is {days} day(s) old.")
    else:
        reasons.append("This credit was added today.")
    if days >= 14 or (days >= 7 and outstanding >= 1000):
        level = "HIGH ATTENTION"
        action = "Send a reminder today."
    elif days >= 7 or outstanding >= 2000:
        level = "MEDIUM ATTENTION"
        action = "Review and consider a reminder."
    else:
        level = "LOW ATTENTION"
        action = "Monitor the balance."
    return {"level": level, "days_overdue": days, "reasons": reasons, "recommended_action": action}
