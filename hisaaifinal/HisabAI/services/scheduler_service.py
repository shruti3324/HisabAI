"""
HisabAI scheduled reminder engine.

Continuously checks the Reminder table and executes reminders
whose scheduled_at time has arrived.

IMPORTANT:
The scheduler executes the EXISTING Reminder record.
It does NOT call send_reminder(), because send_reminder()
creates a new reminder record for an immediate call.
"""

import asyncio
from datetime import datetime

from sqlmodel import select

from db import get_session
from models import Reminder
from services.reminder_service import (
    execute_scheduled_reminder,
)


CHECK_INTERVAL_SECONDS = 15

_scheduler_task = None


async def process_scheduled_reminders():
    """
    Continuously check for due scheduled reminders.
    """

    print(
        "[SCHEDULER] Scheduled reminder engine is running."
    )

    while True:

        try:

            now = datetime.utcnow()

            with get_session() as session:

                reminders = session.exec(
                    select(Reminder)
                    .where(
                        Reminder.status == "scheduled",
                        Reminder.scheduled_at != None,
                        Reminder.scheduled_at <= now,
                    )
                    .order_by(
                        Reminder.scheduled_at
                    )
                ).all()

                reminder_ids = [
                    reminder.id
                    for reminder in reminders
                    if reminder.id is not None
                ]

            # ------------------------------------------------
            # Process outside the first DB session.
            # Each execution gets its own DB session.
            # ------------------------------------------------

            for reminder_id in reminder_ids:

                print(
                    f"[SCHEDULER] Reminder "
                    f"{reminder_id} is due."
                )

                # ------------------------------------------------
                # Claim the reminder.
                #
                # This prevents the same scheduler loop from
                # repeatedly selecting it while it is executing.
                # ------------------------------------------------

                claimed = False

                with get_session() as session:

                    reminder = session.get(
                        Reminder,
                        reminder_id,
                    )

                    if not reminder:
                        continue

                    if reminder.status != "scheduled":
                        continue

                    reminder.status = "queued"

                    session.add(reminder)
                    session.commit()

                    claimed = True

                if not claimed:
                    continue

                # ------------------------------------------------
                # Execute the EXISTING reminder.
                # ------------------------------------------------

                try:

                    result = (
                        execute_scheduled_reminder(
                            reminder_id
                        )
                    )

                    print(
                        f"[SCHEDULER] Reminder "
                        f"{reminder_id} executed."
                    )

                    print(
                        f"[SCHEDULER] Result: "
                        f"{result}"
                    )

                except Exception as exc:

                    print(
                        f"[SCHEDULER] Failed to execute "
                        f"reminder {reminder_id}: {exc}"
                    )

                    with get_session() as error_session:

                        failed_reminder = (
                            error_session.get(
                                Reminder,
                                reminder_id,
                            )
                        )

                        if failed_reminder:

                            failed_reminder.status = (
                                "failed"
                            )

                            failed_reminder.outcome = (
                                f"Scheduled reminder failed: "
                                f"{exc}"
                            )

                            error_session.add(
                                failed_reminder
                            )

                            error_session.commit()

        except asyncio.CancelledError:

            print(
                "[SCHEDULER] Scheduler task cancelled."
            )

            raise

        except Exception as exc:

            print(
                "[SCHEDULER] Scheduler error:",
                exc,
            )

        await asyncio.sleep(
            CHECK_INTERVAL_SECONDS
        )


def start_scheduler():
    """
    Start the background scheduler once.
    """

    global _scheduler_task

    if _scheduler_task is not None:

        print(
            "[SCHEDULER] Scheduler already running."
        )

        return

    try:

        loop = asyncio.get_running_loop()

    except RuntimeError:

        print(
            "[SCHEDULER] No running event loop. "
            "Scheduler was not started."
        )

        return

    _scheduler_task = loop.create_task(
        process_scheduled_reminders()
    )

    print(
        "[SCHEDULER] Background scheduler started."
    )


def stop_scheduler():
    """
    Stop the scheduler if required.
    """

    global _scheduler_task

    if _scheduler_task is not None:

        _scheduler_task.cancel()

        _scheduler_task = None

        print(
            "[SCHEDULER] Background scheduler stopped."
        )