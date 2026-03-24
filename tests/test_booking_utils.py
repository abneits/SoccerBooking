import pytest
from tests.conftest import create_user, create_slot
from backend.booking_utils import create_booking, cancel_booking, get_slot_bookings, BookingError
from backend import db as db_module


async def _book(slot_id, user_id, booked_by_id, btype="player", guest_name=None):
    return await create_booking(slot_id, user_id, booked_by_id, btype, guest_name)


class TestCreateBooking:
    async def test_first_booking_is_confirmed_position_1(self):
        user = await create_user("alice")
        slot = await create_slot("2026-03-25")
        b = await _book(slot["id"], user["id"], user["id"])
        assert b["status"] == "confirmed"
        assert b["position"] == 1

    async def test_position_increments_per_slot(self):
        slot = await create_slot("2026-03-25")
        users = [await create_user(f"u{i}") for i in range(3)]
        bookings = [await _book(slot["id"], u["id"], u["id"]) for u in users]
        assert [b["position"] for b in bookings] == [1, 2, 3]

    async def test_eleventh_booking_goes_to_waitlist(self):
        slot = await create_slot("2026-03-25")
        users = [await create_user(f"u{i}") for i in range(11)]
        bookings = [await _book(slot["id"], u["id"], u["id"]) for u in users]
        assert bookings[9]["status"] == "confirmed"
        assert bookings[10]["status"] == "waitlist"

    async def test_max_waitlist_raises(self):
        slot = await create_slot("2026-03-25")
        users = [await create_user(f"u{i}") for i in range(13)]
        for u in users[:12]:
            await _book(slot["id"], u["id"], u["id"])
        with pytest.raises(BookingError, match="full"):
            await _book(slot["id"], users[12]["id"], users[12]["id"])

    async def test_duplicate_player_booking_raises(self):
        user = await create_user("alice")
        slot = await create_slot("2026-03-25")
        await _book(slot["id"], user["id"], user["id"])
        with pytest.raises(BookingError, match="already booked"):
            await _book(slot["id"], user["id"], user["id"])

    async def test_player_can_add_guest(self):
        player = await create_user("alice")
        slot = await create_slot("2026-03-25")
        g = await _book(slot["id"], None, player["id"], "guest", "Bob Guest")
        assert g["type"] == "guest"
        assert g["guest_name"] == "Bob Guest"
        assert g["user_id"] is None
        assert g["booked_by_id"] == player["id"]

    async def test_guest_requires_name(self):
        player = await create_user("alice")
        slot = await create_slot("2026-03-25")
        with pytest.raises(BookingError, match="guest_name"):
            await _book(slot["id"], None, player["id"], "guest", None)


class TestCancelBooking:
    async def test_cancel_confirmed_promotes_waitlist_entry(self):
        slot = await create_slot("2026-03-25")
        users = [await create_user(f"u{i}") for i in range(11)]
        bookings = [await _book(slot["id"], u["id"], u["id"]) for u in users]
        waitlist_b = bookings[10]
        assert waitlist_b["status"] == "waitlist"

        result = await cancel_booking(bookings[0]["id"], slot["id"])
        assert result is not None
        assert result["promoted"]["id"] == waitlist_b["id"]

        row = await db_module.fetch_one("SELECT data FROM bookings WHERE id = $1", waitlist_b["id"])
        assert row["data"]["status"] == "confirmed"

    async def test_cancel_confirmed_no_waitlist_returns_none(self):
        slot = await create_slot("2026-03-25")
        user = await create_user("alice")
        b = await _book(slot["id"], user["id"], user["id"])
        result = await cancel_booking(b["id"], slot["id"])
        assert result is None
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 0

    async def test_cancel_waitlist_no_promotion(self):
        slot = await create_slot("2026-03-25")
        users = [await create_user(f"u{i}") for i in range(11)]
        bookings = [await _book(slot["id"], u["id"], u["id"]) for u in users]
        waitlist_b = bookings[10]

        result = await cancel_booking(waitlist_b["id"], slot["id"])
        assert result is None
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 10


class TestGetSlotBookings:
    async def test_returns_confirmed_and_waitlist_separated(self):
        slot = await create_slot("2026-03-25")
        users = [await create_user(f"u{i}") for i in range(3)]
        for u in users:
            await _book(slot["id"], u["id"], u["id"])
        result = await get_slot_bookings(slot["id"])
        assert len(result["confirmed"]) == 3
        assert len(result["waitlist"]) == 0
