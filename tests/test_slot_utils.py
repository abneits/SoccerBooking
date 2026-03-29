from datetime import datetime, date
from zoneinfo import ZoneInfo
from backend.slot_utils import compute_slot_state, next_wednesday, SlotState
from backend import db as db_module
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

    def test_from_tuesday(self):
        assert next_wednesday(date(2026, 3, 24)) == date(2026, 3, 25)

    def test_from_friday(self):
        assert next_wednesday(date(2026, 3, 27)) == date(2026, 4, 1)

    def test_from_saturday(self):
        assert next_wednesday(date(2026, 3, 28)) == date(2026, 4, 1)

    def test_from_sunday(self):
        assert next_wednesday(date(2026, 3, 29)) == date(2026, 4, 1)


class TestComputeSlotState:
    def test_open_on_monday_afternoon(self):
        slot = {"date": "2026-03-25", "status": "open"}
        assert compute_slot_state(slot, paris(2026, 3, 23, 14)) == SlotState.OPEN

    def test_open_on_tuesday(self):
        slot = {"date": "2026-03-25", "status": "open"}
        assert compute_slot_state(slot, paris(2026, 3, 24, 10)) == SlotState.OPEN

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
        assert compute_slot_state(slot, paris(2026, 3, 23, 14)) == SlotState.CANCELLED

    def test_cancelled_overrides_closed(self):
        slot = {"date": "2026-03-25", "status": "cancelled"}
        assert compute_slot_state(slot, paris(2026, 3, 25, 18, 30)) == SlotState.CANCELLED

    def test_cancelled_overrides_frozen(self):
        slot = {"date": "2026-03-25", "status": "cancelled"}
        assert compute_slot_state(slot, paris(2026, 3, 25, 20)) == SlotState.CANCELLED

    def test_boundary_exactly_18h_is_closed(self):
        slot = {"date": "2026-03-25", "status": "open"}
        assert compute_slot_state(slot, paris(2026, 3, 25, 18, 0)) == SlotState.CLOSED

    def test_boundary_exactly_19h_is_frozen(self):
        slot = {"date": "2026-03-25", "status": "open"}
        assert compute_slot_state(slot, paris(2026, 3, 25, 19, 0)) == SlotState.FROZEN

    def test_boundary_exactly_monday_noon_is_open(self):
        slot = {"date": "2026-03-25", "status": "open"}
        assert compute_slot_state(slot, paris(2026, 3, 23, 12, 0)) == SlotState.OPEN

    def test_before_monday_noon_is_frozen(self):
        slot = {"date": "2026-03-25", "status": "open"}
        assert compute_slot_state(slot, paris(2026, 3, 23, 11, 59)) == SlotState.FROZEN

    def test_boundary_wednesday_17_59_is_open(self):
        slot = {"date": "2026-03-25", "status": "open"}
        assert compute_slot_state(slot, paris(2026, 3, 25, 17, 59)) == SlotState.OPEN

    def test_boundary_wednesday_18_59_is_closed(self):
        slot = {"date": "2026-03-25", "status": "open"}
        assert compute_slot_state(slot, paris(2026, 3, 25, 18, 59)) == SlotState.CLOSED


class TestGetOrCreateUpcomingSlot:
    async def test_creates_slot_when_none_exists(self):
        from backend.slot_utils import get_or_create_upcoming_slot
        now = paris(2026, 3, 23, 14)
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
        now = paris(2026, 3, 23, 11)
        slot = await get_or_create_upcoming_slot(now)
        assert slot is None

    async def test_returns_none_at_11_59(self):
        from backend.slot_utils import get_or_create_upcoming_slot
        now = paris(2026, 3, 23, 11, 59)
        slot = await get_or_create_upcoming_slot(now)
        assert slot is None

    async def test_creates_at_exactly_noon(self):
        from backend.slot_utils import get_or_create_upcoming_slot
        now = paris(2026, 3, 23, 12, 0)
        slot = await get_or_create_upcoming_slot(now)
        assert slot is not None

    async def test_concurrent_creation_is_idempotent(self):
        import asyncio
        from backend.slot_utils import get_or_create_upcoming_slot
        now = paris(2026, 3, 23, 14)
        await asyncio.gather(
            get_or_create_upcoming_slot(now),
            get_or_create_upcoming_slot(now),
            get_or_create_upcoming_slot(now),
        )
        count = await db_module.fetch_val("SELECT COUNT(*) FROM slots")
        assert count == 1

    async def test_returns_cancelled_slot_if_exists(self):
        from backend.slot_utils import get_or_create_upcoming_slot
        await create_slot("2026-03-25", status="cancelled")
        now = paris(2026, 3, 23, 14)
        slot = await get_or_create_upcoming_slot(now)
        assert slot is not None
        assert slot["status"] == "cancelled"

    async def test_new_slot_has_default_fields(self):
        from backend.slot_utils import get_or_create_upcoming_slot
        now = paris(2026, 3, 23, 14)
        slot = await get_or_create_upcoming_slot(now)
        assert slot["nudge_sent"] is False
        assert slot["cancelled_reason"] is None
        assert slot["details"] == {}
