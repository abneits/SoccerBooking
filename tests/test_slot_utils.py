from datetime import datetime, date
import pytest
from zoneinfo import ZoneInfo
from backend.slot_utils import compute_slot_state, next_wednesday, SlotState
from tests.conftest import create_slot

TZ = ZoneInfo("Europe/Paris")


def paris(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=TZ)


class TestNextWednesday:
    def test_from_monday_returns_same_week_wednesday(self):
        assert next_wednesday(date(2026, 3, 23)) == date(2026, 3, 25)

    def test_from_wednesday_returns_same_day(self):
        assert next_wednesday(date(2026, 3, 25)) == date(2026, 3, 25)

    def test_from_thursday_returns_next_wednesday(self):
        assert next_wednesday(date(2026, 3, 26)) == date(2026, 4, 1)


class TestComputeSlotState:
    def test_open_on_monday_afternoon(self):
        slot = {"date": "2026-03-25", "status": "open"}
        assert compute_slot_state(slot, paris(2026, 3, 23, 14)) == SlotState.OPEN

    def test_open_on_wednesday_morning(self):
        slot = {"date": "2026-03-25", "status": "open"}
        assert compute_slot_state(slot, paris(2026, 3, 25, 10)) == SlotState.OPEN

    def test_closed_wednesday_18_30(self):
        slot = {"date": "2026-03-25", "status": "open"}
        assert compute_slot_state(slot, paris(2026, 3, 25, 18, 30)) == SlotState.CLOSED

    def test_frozen_wednesday_after_19(self):
        slot = {"date": "2026-03-25", "status": "open"}
        assert compute_slot_state(slot, paris(2026, 3, 25, 20)) == SlotState.FROZEN

    def test_frozen_on_sunday(self):
        slot = {"date": "2026-03-25", "status": "open"}
        assert compute_slot_state(slot, paris(2026, 3, 29, 12)) == SlotState.FROZEN

    def test_cancelled_overrides_time_state(self):
        slot = {"date": "2026-03-25", "status": "cancelled"}
        # Would be OPEN by time, but status=cancelled wins
        assert compute_slot_state(slot, paris(2026, 3, 23, 14)) == SlotState.CANCELLED

    def test_boundary_exactly_18h_is_closed(self):
        slot = {"date": "2026-03-25", "status": "open"}
        assert compute_slot_state(slot, paris(2026, 3, 25, 18, 0)) == SlotState.CLOSED

    def test_boundary_exactly_19h_is_frozen(self):
        slot = {"date": "2026-03-25", "status": "open"}
        assert compute_slot_state(slot, paris(2026, 3, 25, 19, 0)) == SlotState.FROZEN

    def test_before_monday_noon_is_frozen(self):
        slot = {"date": "2026-03-25", "status": "open"}
        assert compute_slot_state(slot, paris(2026, 3, 23, 11, 59)) == SlotState.FROZEN


class TestGetOrCreateUpcomingSlot:
    async def test_creates_slot_when_none_exists(self):
        from backend.slot_utils import get_or_create_upcoming_slot
        now = paris(2026, 3, 23, 14)  # Monday after noon
        slot = await get_or_create_upcoming_slot(now)
        assert slot is not None
        assert slot["date"] == "2026-03-25"
        assert slot["status"] == "open"

    async def test_returns_existing_slot(self):
        from backend.slot_utils import get_or_create_upcoming_slot
        await create_slot("2026-03-25")
        now = paris(2026, 3, 23, 14)
        slot = await get_or_create_upcoming_slot(now)
        assert slot["date"] == "2026-03-25"

    async def test_returns_none_before_monday_noon(self):
        from backend.slot_utils import get_or_create_upcoming_slot
        now = paris(2026, 3, 23, 11)  # Monday before noon
        slot = await get_or_create_upcoming_slot(now)
        assert slot is None

    async def test_concurrent_creation_is_idempotent(self):
        """Concurrent calls must not create duplicate slots."""
        import asyncio
        from backend.slot_utils import get_or_create_upcoming_slot
        from backend import db as db_module
        now = paris(2026, 3, 23, 14)
        await asyncio.gather(
            get_or_create_upcoming_slot(now),
            get_or_create_upcoming_slot(now),
            get_or_create_upcoming_slot(now),
        )
        count = await db_module.fetch_val("SELECT COUNT(*) FROM slots")
        assert count == 1
