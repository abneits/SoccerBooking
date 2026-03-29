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

    async def test_tenth_booking_is_confirmed(self):
        slot = await create_slot("2026-03-25")
        users = [await create_user(f"u{i}") for i in range(10)]
        bookings = [await _book(slot["id"], u["id"], u["id"]) for u in users]
        assert bookings[9]["status"] == "confirmed"

    async def test_eleventh_booking_goes_to_waitlist(self):
        slot = await create_slot("2026-03-25")
        users = [await create_user(f"u{i}") for i in range(11)]
        bookings = [await _book(slot["id"], u["id"], u["id"]) for u in users]
        assert bookings[9]["status"] == "confirmed"
        assert bookings[10]["status"] == "waitlist"

    async def test_twelfth_booking_goes_to_waitlist(self):
        slot = await create_slot("2026-03-25")
        users = [await create_user(f"u{i}") for i in range(12)]
        bookings = [await _book(slot["id"], u["id"], u["id"]) for u in users]
        assert bookings[11]["status"] == "waitlist"

    async def test_thirteenth_booking_raises_full(self):
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

    async def test_player_can_book_self_and_guest(self):
        player = await create_user("alice")
        slot = await create_slot("2026-03-25")
        b1 = await _book(slot["id"], player["id"], player["id"], "player")
        b2 = await _book(slot["id"], None, player["id"], "guest", "Bob")
        assert b1["type"] == "player"
        assert b2["type"] == "guest"
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 2

    async def test_bookings_on_different_slots_are_independent(self):
        user = await create_user("alice")
        slot1 = await create_slot("2026-03-25")
        slot2 = await create_slot("2026-04-01")
        await _book(slot1["id"], user["id"], user["id"])
        b2 = await _book(slot2["id"], user["id"], user["id"])
        assert b2["status"] == "confirmed"

    async def test_booking_has_created_at(self):
        user = await create_user("alice")
        slot = await create_slot("2026-03-25")
        b = await _book(slot["id"], user["id"], user["id"])
        assert "created_at" in b

    async def test_admin_can_book_for_another_user(self):
        admin = await create_user("admin", role="admin")
        player = await create_user("bob")
        slot = await create_slot("2026-03-25")
        b = await _book(slot["id"], player["id"], admin["id"])
        assert b["user_id"] == player["id"]
        assert b["booked_by_id"] == admin["id"]


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

    async def test_promotes_lowest_position_waitlist_entry(self):
        slot = await create_slot("2026-03-25")
        users = [await create_user(f"u{i}") for i in range(12)]
        bookings = [await _book(slot["id"], u["id"], u["id"]) for u in users]
        # u10 (pos 11) and u11 (pos 12) are waitlisted
        result = await cancel_booking(bookings[0]["id"], slot["id"])
        # u10 should be promoted (lower position), not u11
        assert result["promoted"]["id"] == bookings[10]["id"]

    async def test_cancel_guest_booking(self):
        player = await create_user("alice")
        slot = await create_slot("2026-03-25")
        g = await _book(slot["id"], None, player["id"], "guest", "Bob")
        result = await cancel_booking(g["id"], slot["id"])
        assert result is None
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 0

    async def test_confirmed_count_after_promotion(self):
        slot = await create_slot("2026-03-25")
        users = [await create_user(f"u{i}") for i in range(11)]
        bookings = [await _book(slot["id"], u["id"], u["id"]) for u in users]
        await cancel_booking(bookings[0]["id"], slot["id"])
        result = await get_slot_bookings(slot["id"])
        assert len(result["confirmed"]) == 10
        assert len(result["waitlist"]) == 0


class TestGetSlotBookings:
    async def test_returns_confirmed_and_waitlist_separated(self):
        slot = await create_slot("2026-03-25")
        users = [await create_user(f"u{i}") for i in range(3)]
        for u in users:
            await _book(slot["id"], u["id"], u["id"])
        result = await get_slot_bookings(slot["id"])
        assert len(result["confirmed"]) == 3
        assert len(result["waitlist"]) == 0

    async def test_empty_slot_returns_empty_lists(self):
        slot = await create_slot("2026-03-25")
        result = await get_slot_bookings(slot["id"])
        assert result["confirmed"] == []
        assert result["waitlist"] == []

    async def test_mixed_confirmed_and_waitlist(self):
        slot = await create_slot("2026-03-25")
        users = [await create_user(f"u{i}") for i in range(11)]
        for u in users:
            await _book(slot["id"], u["id"], u["id"])
        result = await get_slot_bookings(slot["id"])
        assert len(result["confirmed"]) == 10
        assert len(result["waitlist"]) == 1

    async def test_bookings_ordered_by_position(self):
        slot = await create_slot("2026-03-25")
        users = [await create_user(f"u{i}") for i in range(3)]
        for u in users:
            await _book(slot["id"], u["id"], u["id"])
        result = await get_slot_bookings(slot["id"])
        positions = [b["position"] for b in result["confirmed"]]
        assert positions == sorted(positions)

    async def test_includes_guest_bookings(self):
        player = await create_user("alice")
        slot = await create_slot("2026-03-25")
        await _book(slot["id"], player["id"], player["id"], "player")
        await _book(slot["id"], None, player["id"], "guest", "Bob")
        result = await get_slot_bookings(slot["id"])
        assert len(result["confirmed"]) == 2
        types = {b["type"] for b in result["confirmed"]}
        assert types == {"player", "guest"}
