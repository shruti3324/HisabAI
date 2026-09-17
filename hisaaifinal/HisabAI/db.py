"""Database setup and non-destructive schema initialisation."""

import os

from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./ledger.db"
)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)


def get_session():
    return Session(engine)


def init_db() -> None:
    import models  # noqa: F401

    SQLModel.metadata.create_all(engine)

    if DATABASE_URL.startswith("sqlite"):
        with engine.begin() as connection:

            # -----------------------------
            # CUSTOMER MIGRATIONS
            # -----------------------------
            customer_columns = {
                row[1]
                for row in connection.execute(
                    text("PRAGMA table_info(customer)")
                )
            }

            customer_additions = {
                "reminder_channel": "TEXT DEFAULT 'demo'",
                "reminder_frequency_days": "INTEGER DEFAULT 3",
                "quiet_hours": "TEXT",
                "last_reminder_at": "DATETIME",
                "reminder_count": "INTEGER DEFAULT 0",
                "promise_to_pay_date": "DATE",
            }

            for name, definition in customer_additions.items():
                if name not in customer_columns:
                    connection.execute(
                        text(
                            f"ALTER TABLE customer "
                            f"ADD COLUMN {name} {definition}"
                        )
                    )

            # -----------------------------
            # REMINDER MIGRATIONS
            # -----------------------------
            reminder_columns = {
                row[1]
                for row in connection.execute(
                    text("PRAGMA table_info(reminder)")
                )
            }

            reminder_additions = {
                "provider_message_id": "TEXT",
                "provider_call_id": "TEXT",
                "attempt_number": "INTEGER DEFAULT 1",
                "scheduled_at": "DATETIME",
                "sent_at": "DATETIME",
                "ai_decision": "TEXT",
                "promise_to_pay_date": "DATE",
            }

            for name, definition in reminder_additions.items():
                if name not in reminder_columns:
                    connection.execute(
                        text(
                            f"ALTER TABLE reminder "
                            f"ADD COLUMN {name} {definition}"
                        )
                    )

            # -----------------------------
            # PAYMENT MIGRATIONS
            # -----------------------------
            payment_columns = {
                row[1]
                for row in connection.execute(
                    text("PRAGMA table_info(payment)")
                )
            }

            payment_additions = {
                "provider_payment_id": "TEXT",
                "provider_order_id": "TEXT",
                "payment_link_url": "TEXT",
                "currency": "TEXT DEFAULT 'INR'",
                "ledger_transaction_id": "INTEGER",
            }

            for name, definition in payment_additions.items():
                if name not in payment_columns:
                    connection.execute(
                        text(
                            f"ALTER TABLE payment "
                            f"ADD COLUMN {name} {definition}"
                        )
                    )