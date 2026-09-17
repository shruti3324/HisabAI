"""Natural language is mapped to a small allow-list of read-only business functions."""
import json
import os
from openai import OpenAI
from db import get_session
from models import AIQuery
from services.analytics_service import customer_transactions, dashboard_summary, overdue_customers, top_debtors
from services.customer_service import customer_matches
from services.transaction_service import customer_summary

def _client() -> OpenAI:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not configured")
    return OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
ALLOWED = {"top_debtors", "above_outstanding", "total_outstanding", "sales_today", "received_today", "customer_balance", "customer_transactions", "overdue", "monthly_sales", "reminder_priority"}
PROMPT = '''Classify this ledger question. Return JSON only: {"intent":"top_debtors|above_outstanding|total_outstanding|sales_today|received_today|customer_balance|customer_transactions|overdue|monthly_sales|reminder_priority", "amount":number|null, "customer":string|null, "days":number|null}.
Never produce SQL. Hindi, Marathi and English are allowed. Question: {query}'''


def _fallback(query: str) -> dict:
    text = query.casefold()
    if any(x in text for x in ["who owes", "kaun", "kisko"]): return {"intent": "top_debtors"}
    if any(x in text for x in ["remind", "yaad", "स्मरण"]): return {"intent": "reminder_priority"}
    if any(x in text for x in ["month", "mahina", "महीना"]): return {"intent": "monthly_sales"}
    if any(x in text for x in ["udhaar", "outstanding", "stuck"]): return {"intent": "total_outstanding"}
    if any(x in text for x in ["received", "receive", "collection"]): return {"intent": "received_today"}
    return {"intent": "sales_today"}


def looks_like_business_question(transcript: str, extraction: dict | None = None) -> bool:
    """Route a spoken question to read-only analytics rather than the transaction form.

    This is deliberately conservative: an extraction with a real amount remains
    a transaction, and an uncertain utterance can still be reviewed by a human.
    """
    if extraction and extraction.get("total_amount") not in (None, "", 0):
        return False
    text = transcript.casefold().strip()
    question_markers = (
        "who", "what", "how much", "show", "owe", "remind", "sales", "received",
        "kaun", "kitna", "kisko", "dikhao", "udhaar", "baaki", "कौन", "कितना",
        "बाकी", "उधार", "कोण", "किती", "बाकीचे", "विक्री",
    )
    return "?" in text or any(marker in text for marker in question_markers)


def answer_business_query(query: str, user_id: str = "demo") -> dict:
    try:
        response = _client().chat.completions.create(model="qwen/qwen3.8-27b", temperature=0, response_format={"type":"json_object"}, messages=[{"role":"user", "content":PROMPT.format(query=query)}])
        plan = json.loads(response.choices[0].message.content)
        if plan.get("intent") not in ALLOWED: plan = _fallback(query)
    except Exception:
        plan = _fallback(query)
    with get_session() as session:
        session.add(AIQuery(user_id=user_id, query_text=query, intent=plan["intent"])); session.commit()
        if plan["intent"] in {"customer_balance", "customer_transactions"} and plan.get("customer"):
            matches = customer_matches(session, user_id, plan["customer"])
            if len(matches) != 1: return {"kind":"clarification", "message":"Which customer do you mean?", "customers":[c.name for c in matches]}
            customer = matches[0]
            summary = customer_summary(customer, user_id)
            if plan["intent"] == "customer_transactions":
                transactions = customer_transactions(customer.id, user_id)
                return {"kind":"customer_transactions", "customer":summary, "transactions":[t.model_dump() for t in transactions], "message":f"{customer.name} has {len(transactions)} active ledger transaction(s)."}
            return {"kind":"customer", "customer":summary, "message":f"{customer.name}'s outstanding balance is ₹{summary['outstanding_amount']:,.0f}."}
    stats = dashboard_summary(user_id)
    intent = plan["intent"]
    if intent == "top_debtors":
        debtors = top_debtors(user_id); return {"kind":"debtors", "customers":debtors, "message": "No one has outstanding credit." if not debtors else f"{debtors[0]['name']} owes you the most — ₹{debtors[0]['outstanding_amount']:,.0f}."}
    if intent == "above_outstanding":
        amount = float(plan.get("amount") or 0); customers = top_debtors(user_id, amount)
        return {"kind":"debtors", "customers":customers, "message":f"{len(customers)} customer(s) owe more than ₹{amount:,.0f}."}
    if intent == "total_outstanding": return {"kind":"metric", "message":f"Your total outstanding amount is ₹{stats['outstanding_udhaar']:,.0f}."}
    if intent == "received_today": return {"kind":"metric", "message":f"You received ₹{stats['received_today']:,.0f} today."}
    if intent == "overdue":
        customers = overdue_customers(int(plan.get("days") or 0), user_id); return {"kind":"debtors", "customers":customers, "message":f"{len(customers)} customer(s) need follow-up."}
    if intent == "reminder_priority":
        customers = overdue_customers(1, user_id) or top_debtors(user_id)
        return {"kind":"debtors", "customers":customers, "message":"No reminders are needed." if not customers else f"Start with {customers[0]['name']} — ₹{customers[0]['outstanding_amount']:,.0f} is outstanding."}
    if intent == "monthly_sales":
        # This MVP's month total is database-derived from the current calendar month.
        from datetime import datetime, timezone
        from services.analytics_service import _transactions
        now = datetime.now(timezone.utc)
        amount = sum(t.total_amount for t in _transactions(user_id) if t.created_at.year == now.year and t.created_at.month == now.month and t.transaction_type in {"sale", "credit_sale"})
        return {"kind":"metric", "message":f"You sold ₹{amount:,.0f} this month."}
    return {"kind":"metric", "message":f"You sold ₹{stats['today_sales']:,.0f} today."}
