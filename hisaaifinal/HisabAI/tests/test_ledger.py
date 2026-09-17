import db
from sqlmodel import SQLModel, create_engine
from services.analytics_service import dashboard_summary, top_debtors
from services.transaction_service import create_transaction, get_customer_ledger, list_customer_summaries, reverse_transaction
from services.validation_service import ValidationError, validate_transaction
from services.language_service import normalize_spoken_numbers
from services.risk_service import reminder_priority
from services.query_service import looks_like_business_question
from services.reminder_service import send_demo_reminder, update_reminder_settings
from services.payment_service import create_demo_payment_request, verify_demo_payment


def setup_function():
    db.engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(db.engine)


def sale(customer, total, paid=0):
    return create_transaction({"customer_name": customer, "total_amount": total, "paid_amount": paid,
        "transaction_type": "credit_sale" if paid < total else "sale"})


def payment(customer, amount):
    return create_transaction({"customer_name": customer, "total_amount": amount, "transaction_type": "payment"})


def test_partial_payment_leaves_correct_outstanding():
    sale("Ramesh", 500, 200)
    assert list_customer_summaries()[0]["outstanding_amount"] == 300


def test_full_payment_settles_account():
    sale("Ramesh", 500)
    payment("Ramesh", 500)
    assert list_customer_summaries()[0]["outstanding_amount"] == 0


def test_additional_credit_increases_outstanding_and_prevents_duplicate_customer():
    sale("Ramesh", 500, 200)
    sale(" ramesh ", 300)
    customers = list_customer_summaries()
    assert len(customers) == 1
    assert customers[0]["outstanding_amount"] == 600


def test_payment_reduces_outstanding():
    sale("Ramesh", 1000)
    payment("Ramesh", 400)
    assert list_customer_summaries()[0]["outstanding_amount"] == 600


def test_validation_rejects_invalid_financial_math():
    try:
        validate_transaction({"customer_name":"Ramesh", "transaction_type":"sale", "total_amount":500, "paid_amount":600})
        assert False, "Expected validation error"
    except ValidationError:
        pass


def test_undo_reverses_balance_without_deleting_audit_record():
    txn = sale("Ramesh", 500)
    reverse_transaction(txn.id)
    assert list_customer_summaries()[0]["outstanding_amount"] == 0


def test_business_metrics_are_database_backed():
    sale("Ramesh", 900)
    sale("Amit", 400)
    assert dashboard_summary()["outstanding_udhaar"] == 1300
    assert top_debtors()[0]["name"] == "Ramesh"


def test_customer_ledger_shows_running_balance_after_sales_and_payment():
    sale("Ramesh", 500, 200)
    payment("Ramesh", 100)
    customer_id = list_customer_summaries()[0]["id"]
    ledger = get_customer_ledger(customer_id)
    # Returned newest first: payment leaves 200 outstanding; original sale left 300.
    assert ledger[0]["transaction_type"] == "payment"
    assert ledger[0]["balance_after"] == 200
    assert ledger[1]["balance_after"] == 300


def test_multilingual_spoken_numbers_normalize_before_financial_processing():
    # These represent Hindi, Marathi, Hinglish, English and code-switched STT output.
    examples = [
        ("paanch sau rupaye", "500 rupaye"),
        ("do sau cash", "200 cash"),
        ("paanchshe rupaycha maal", "500 rupaycha maal"),
        ("donshe dile", "200 dile"),
        ("one hundred rupees", "100 rupees"),
        ("two hundred fifty cash", "250 cash"),
        ("panch sau aur do sau", "500 aur 200"),
        ("five hundred and twenty rupees", "520 rupees"),
        ("हजार रुपये", "1000 रुपये"),
        ("पांच सौ रुपये", "500 रुपये"),
        ("दो सौ cash", "200 cash"),
        ("पाचशे रुपय", "500 रुपय"),
        ("दोनशे दिले", "200 दिले"),
        ("shambar rupaye", "100 rupaye"),
        ("sahashe cash", "600 cash"),
        ("seven hundred payment", "700 payment"),
        ("nau sau udhaar", "900 udhaar"),
        ("चार सौ बाकी", "400 बाकी"),
        ("teen sau paid", "300 paid"),
        ("aath she rupaye", "800 rupaye"),
    ]
    for spoken, expected in examples:
        assert normalize_spoken_numbers(spoken) == expected


def test_priority_is_explainable_and_not_a_credit_score():
    sale("Ramesh", 2500)
    customer = list_customer_summaries()[0]
    priority = reminder_priority(customer)
    assert priority["level"] in {"LOW ATTENTION", "MEDIUM ATTENTION", "HIGH ATTENTION"}
    assert priority["reasons"]
    assert "credit" not in priority["level"].lower()


def test_spoken_business_questions_route_to_safe_assistant_but_transactions_do_not():
    assert looks_like_business_question("Who owes me more than 500?", {"total_amount": None})
    assert looks_like_business_question("Ramesh ka kitna baaki hai", {"total_amount": None})
    assert looks_like_business_question("Aaj kisko remind karu", {"total_amount": None})
    assert not looks_like_business_question("Ramesh ne 500 ka maal liya", {"total_amount": 500})


def test_demo_reminder_requires_consent_and_respects_settings():
    sale("Ramesh", 500)
    customer_id = list_customer_summaries()[0]["id"]
    try:
        send_demo_reminder(customer_id)
        assert False, "Reminder without consent must be blocked"
    except ValueError:
        pass
    update_reminder_settings(customer_id, {"reminder_enabled": True, "reminder_consent": True,
        "preferred_language": "Hindi", "reminder_frequency_days": 3})
    reminder = send_demo_reminder(customer_id)
    assert reminder.channel == "demo"
    assert "Ramesh" in reminder.message


def test_demo_payment_requires_server_verification_and_is_idempotent():
    sale("Ramesh", 500)
    customer_id = list_customer_summaries()[0]["id"]
    request = create_demo_payment_request(customer_id, 500)
    assert request.status == "pending"
    verified = verify_demo_payment(request.provider_reference)
    assert verified.status == "verified"
    # A duplicate verification must not create another payment transaction.
    verify_demo_payment(request.provider_reference)
    assert list_customer_summaries()[0]["outstanding_amount"] == 0
