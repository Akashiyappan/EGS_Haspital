"""Send appointment reminders. Idempotent; schedule it every 5-15 minutes
(e.g. with cron or another scheduler)."""

import asyncio

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal, engine
from app.services.appointment_service import send_due_reminders


async def main() -> None:
    configure_logging(settings.LOG_LEVEL, settings.LOG_JSON)
    async with SessionLocal() as db:
        sent = await send_due_reminders(db)
    print(f"Reminders sent for {sent} appointment(s)")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
