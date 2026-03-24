from datetime import datetime, date, timedelta
from enum import Enum
from zoneinfo import ZoneInfo
import asyncpg
import json

from backend import db as db_module
from backend.config import TIMEZONE


class SlotState(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    FROZEN = "frozen"
    CANCELLED = "cancelled"


def next_wednesday(from_date: date) -> date:
    """Return the next Wednesday on or after from_date."""
    days_ahead = (2 - from_date.weekday()) % 7  # Wednesday = weekday 2
    return from_date + timedelta(days=days_ahead)


def compute_slot_state(slot: dict, now: datetime) -> SlotState:
    """Derive slot state from slot data and current time.

    States:
    - CANCELLED: slot.status == 'cancelled' (overrides everything)
    - OPEN: Mon 12:00 <= now < Wed 18:00
    - CLOSED: Wed 18:00 <= now < Wed 19:00 (admin only)
    - FROZEN: now < Mon 12:00 OR now >= Wed 19:00 (read-only for all)
    """
    if slot["status"] == "cancelled":
        return SlotState.CANCELLED

    tz = ZoneInfo(TIMEZONE)
    slot_date = date.fromisoformat(slot["date"])
    wednesday = datetime(slot_date.year, slot_date.month, slot_date.day, tzinfo=tz)
    monday = wednesday - timedelta(days=2)

    monday_noon = monday.replace(hour=12, minute=0, second=0, microsecond=0)
    wednesday_18h = wednesday.replace(hour=18, minute=0, second=0, microsecond=0)
    wednesday_19h = wednesday.replace(hour=19, minute=0, second=0, microsecond=0)

    if now < monday_noon:
        return SlotState.FROZEN
    if now < wednesday_18h:
        return SlotState.OPEN
    if now < wednesday_19h:
        return SlotState.CLOSED
    return SlotState.FROZEN


async def get_or_create_upcoming_slot(now: datetime) -> dict | None:
    """Return the upcoming Wednesday slot, creating it if Monday >= noon.

    Returns None before Monday noon.
    Handles concurrent creation via UniqueViolationError (unique index on date).
    """
    tz = ZoneInfo(TIMEZONE)
    today = now.date()
    wednesday = next_wednesday(today)
    monday = wednesday - timedelta(days=2)
    monday_noon = datetime(monday.year, monday.month, monday.day, 12, tzinfo=tz)

    if now < monday_noon:
        return None

    date_str = wednesday.isoformat()

    # Try to fetch existing slot
    row = await db_module.fetch_one(
        "SELECT id, data FROM slots WHERE data->>'date' = $1", date_str
    )
    if row:
        return {"id": row["id"], **row["data"]}

    # Try to insert — silently handle duplicate (concurrent request race)
    try:
        data = json.dumps({
            "date": date_str,
            "status": "open",
            "cancelled_reason": None,
            "nudge_sent": False,
            "details": {},
        })
        row = await db_module.fetch_one(
            "INSERT INTO slots (data) VALUES ($1::jsonb) RETURNING id, data", data
        )
        return {"id": row["id"], **row["data"]}
    except asyncpg.UniqueViolationError:
        # Another concurrent request created the slot first — fetch it
        row = await db_module.fetch_one(
            "SELECT id, data FROM slots WHERE data->>'date' = $1", date_str
        )
        return {"id": row["id"], **row["data"]}
