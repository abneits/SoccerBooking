import logging
from datetime import date
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.config import TIMEZONE

_scheduler: AsyncIOScheduler | None = None
logger = logging.getLogger(__name__)


async def _nudge_job() -> None:
    """Wednesday 14:00 job: fire slot_not_full webhook if slot is open and not full."""
    import json
    from backend import db as db_module
    from backend.webhooks import fire_slot_not_full

    tz = ZoneInfo(TIMEZONE)
    today = date.today()

    # Guard: only run on Wednesdays (cron should handle this, but be safe)
    if today.weekday() != 2:
        return

    date_str = today.isoformat()
    row = await db_module.fetch_one(
        "SELECT id, data FROM slots WHERE data->>'date' = $1", date_str
    )
    if not row:
        logger.info("Nudge job: no slot found for %s", date_str)
        return

    slot = {"id": row["id"], **row["data"]}

    if slot["status"] != "open":
        return
    if slot.get("nudge_sent"):
        return

    confirmed_count = await db_module.fetch_val(
        "SELECT COUNT(*) FROM bookings "
        "WHERE (data->>'slot_id')::int = $1 AND data->>'status' = 'confirmed'",
        slot["id"],
    )

    if confirmed_count >= 10:
        return

    await fire_slot_not_full(date_str, confirmed_count)

    updated = {k: v for k, v in slot.items() if k != "id"}
    updated["nudge_sent"] = True
    await db_module.execute(
        "UPDATE slots SET data = $1::jsonb WHERE id = $2",
        json.dumps(updated),
        slot["id"],
    )
    logger.info("Nudge sent for %s: %d confirmed", date_str, confirmed_count)


def start_scheduler() -> None:
    global _scheduler
    tz = ZoneInfo(TIMEZONE)
    _scheduler = AsyncIOScheduler(timezone=tz)
    _scheduler.add_job(
        _nudge_job,
        CronTrigger(day_of_week="wed", hour=14, minute=0, timezone=tz),
        id="wednesday_nudge",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
