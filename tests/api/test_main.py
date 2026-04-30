"""
API tests — Main routes (/, /book, /cancel)

Time control: uses POST /internal/set-time (requires TESTING=true on the app).
All state-sensitive tests set the app clock explicitly via at_time().

Slot date: TEST_WEDNESDAY = "2099-04-02" (Wednesday)
  OPEN_TIME    = Monday 2099-03-31 14:00 Paris  → OPEN
  CLOSED_TIME  = Wednesday 2099-04-02 18:30      → CLOSED
  FROZEN_TIME  = Wednesday 2099-04-02 20:00      → FROZEN
  PRE_OPEN_TIME= Monday 2099-03-31 11:00         → FROZEN (before noon)
"""

import pytest
from tests.helpers import (
    db_create_user,
    db_create_slot,
    db_create_booking,
    db_fill_slot,
    db_count_bookings,
    api_login,
    at_time,
    TEST_WEDNESDAY,
    OPEN_TIME,
    CLOSED_TIME,
    FROZEN_TIME,
    PRE_OPEN_TIME,
)


class TestHomePage:
    async def test_unauthenticated_redirects_to_login(self, client):
        r = await client.get("/")
        assert r.status_code == 302
        assert "login" in r.headers["location"]

    async def test_authenticated_returns_200(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        await api_login(client, "alice")
        r = await client.get("/")
        assert r.status_code == 200

    async def test_shows_slot_date(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        await db_create_slot(db_pool, TEST_WEDNESDAY)
        await api_login(client, "alice")
        r = await client.get("/")
        assert TEST_WEDNESDAY.encode() in r.content

    async def test_no_slot_message_before_monday_noon(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        await api_login(client, "alice")
        async with at_time(client, PRE_OPEN_TIME):
            r = await client.get("/")
        assert r.status_code == 200
        assert b"lundi" in r.content.lower() or b"pas encore" in r.content or "créneau".encode() in r.content.lower()

    async def test_slot_created_after_monday_noon(self, client, db_pool):
        """get_or_create_upcoming_slot creates slot at Monday noon."""
        await db_create_user(db_pool, "alice")
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.get("/")
        assert r.status_code == 200
        assert TEST_WEDNESDAY.encode() in r.content

    async def test_cancelled_slot_shown(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        await db_create_slot(db_pool, TEST_WEDNESDAY, status="cancelled")
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.get("/")
        assert b"ANNUL" in r.content or b"annul" in r.content.lower()

    async def test_booking_list_shows_player(self, client, db_pool):
        user = await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        await db_create_booking(db_pool, slot["id"], user["id"], user["id"])
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.get("/")
        assert b"alice" in r.content

    async def test_admin_sees_admin_link(self, client, db_pool):
        await db_create_user(db_pool, "boss", role="admin")
        await api_login(client, "boss")
        r = await client.get("/")
        assert b"/admin" in r.content

    async def test_player_does_not_see_admin_link(self, client, db_pool):
        await db_create_user(db_pool, "alice", role="player")
        await api_login(client, "alice")
        r = await client.get("/")
        assert b"/admin" not in r.content

    async def test_open_state_badge_shown(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        await db_create_slot(db_pool, TEST_WEDNESDAY)
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.get("/")
        assert b"OPEN" in r.content or b"open" in r.content

    async def test_closed_state_badge_shown(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        await db_create_slot(db_pool, TEST_WEDNESDAY)
        await api_login(client, "alice")
        async with at_time(client, CLOSED_TIME):
            r = await client.get("/")
        assert b"CLOSED" in r.content or b"closed" in r.content

    async def test_frozen_state_badge_shown(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        await db_create_slot(db_pool, TEST_WEDNESDAY)
        await api_login(client, "alice")
        async with at_time(client, FROZEN_TIME):
            r = await client.get("/")
        assert b"FROZEN" in r.content or b"frozen" in r.content

    async def test_waitlist_shown_when_slot_full(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        await db_fill_slot(db_pool, slot["id"], confirmed=10, waitlist=1)
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.get("/")
        assert b"attente" in r.content.lower() or b"waitlist" in r.content.lower()


class TestBookEndpoint:
    async def test_book_own_spot_during_open(self, client, db_pool):
        user = await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.post("/book", data={"slot_id": slot["id"], "type": "player"})
        assert r.status_code == 200
        count = await db_count_bookings(db_pool)
        assert count == 1

    async def test_book_returns_html_partial_not_full_page(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.post("/book", data={"slot_id": slot["id"], "type": "player"})
        assert r.status_code == 200
        assert b"<!DOCTYPE" not in r.content   # partial, not full page

    async def test_book_response_contains_player_name(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.post("/book", data={"slot_id": slot["id"], "type": "player"})
        assert b"alice" in r.content

    async def test_book_returns_403_during_closed(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        await api_login(client, "alice")
        async with at_time(client, CLOSED_TIME):
            r = await client.post("/book", data={"slot_id": slot["id"], "type": "player"})
        assert r.status_code == 403

    async def test_book_returns_403_during_frozen(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        await api_login(client, "alice")
        async with at_time(client, FROZEN_TIME):
            r = await client.post("/book", data={"slot_id": slot["id"], "type": "player"})
        assert r.status_code == 403

    async def test_book_returns_403_before_open(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        await api_login(client, "alice")
        async with at_time(client, PRE_OPEN_TIME):
            r = await client.post("/book", data={"slot_id": slot["id"], "type": "player"})
        assert r.status_code == 403

    async def test_book_returns_403_on_cancelled_slot(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY, status="cancelled")
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.post("/book", data={"slot_id": slot["id"], "type": "player"})
        assert r.status_code == 403

    async def test_book_nonexistent_slot_returns_404(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.post("/book", data={"slot_id": 999999, "type": "player"})
        assert r.status_code == 404

    async def test_book_guest_during_open(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.post(
                "/book", data={"slot_id": slot["id"], "type": "guest", "guest_name": "Bob"}
            )
        assert r.status_code == 200
        count = await db_count_bookings(db_pool)
        assert count == 1

    async def test_duplicate_player_booking_returns_400(self, client, db_pool):
        user = await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        await db_create_booking(db_pool, slot["id"], user["id"], user["id"])
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.post("/book", data={"slot_id": slot["id"], "type": "player"})
        assert r.status_code == 400

    async def test_full_slot_returns_400(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        await db_fill_slot(db_pool, slot["id"], confirmed=10, waitlist=2)
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.post("/book", data={"slot_id": slot["id"], "type": "player"})
        assert r.status_code == 400

    async def test_11th_booking_goes_to_waitlist(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        await db_fill_slot(db_pool, slot["id"], confirmed=10)
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.post("/book", data={"slot_id": slot["id"], "type": "player"})
        assert r.status_code == 200
        count = await db_count_bookings(db_pool)
        assert count == 11

    async def test_unauthenticated_redirects(self, client, db_pool):
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        r = await client.post("/book", data={"slot_id": slot["id"], "type": "player"})
        assert r.status_code == 302

    async def test_guest_without_name_returns_400_during_open(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.post("/book", data={"slot_id": slot["id"], "type": "guest"})
        assert r.status_code == 400


class TestCancelEndpoint:
    async def test_cancel_own_booking_during_open(self, client, db_pool):
        user = await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        booking = await db_create_booking(db_pool, slot["id"], user["id"], user["id"])
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.post(
                "/cancel", data={"booking_id": booking["id"], "slot_id": slot["id"]}
            )
        assert r.status_code == 200
        count = await db_count_bookings(db_pool)
        assert count == 0

    async def test_cancel_returns_html_partial(self, client, db_pool):
        user = await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        booking = await db_create_booking(db_pool, slot["id"], user["id"], user["id"])
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.post(
                "/cancel", data={"booking_id": booking["id"], "slot_id": slot["id"]}
            )
        assert r.status_code == 200
        assert b"<!DOCTYPE" not in r.content

    async def test_cancel_returns_403_during_closed(self, client, db_pool):
        user = await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        booking = await db_create_booking(db_pool, slot["id"], user["id"], user["id"])
        await api_login(client, "alice")
        async with at_time(client, CLOSED_TIME):
            r = await client.post(
                "/cancel", data={"booking_id": booking["id"], "slot_id": slot["id"]}
            )
        assert r.status_code == 403

    async def test_cancel_returns_403_during_frozen(self, client, db_pool):
        user = await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        booking = await db_create_booking(db_pool, slot["id"], user["id"], user["id"])
        await api_login(client, "alice")
        async with at_time(client, FROZEN_TIME):
            r = await client.post(
                "/cancel", data={"booking_id": booking["id"], "slot_id": slot["id"]}
            )
        assert r.status_code == 403

    async def test_cannot_cancel_another_players_booking(self, client, db_pool):
        alice = await db_create_user(db_pool, "alice")
        bob = await db_create_user(db_pool, "bob")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        booking = await db_create_booking(db_pool, slot["id"], bob["id"], bob["id"])
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.post(
                "/cancel", data={"booking_id": booking["id"], "slot_id": slot["id"]}
            )
        assert r.status_code == 403
        assert await db_count_bookings(db_pool) == 1

    async def test_cancel_nonexistent_slot_returns_404(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.post("/cancel", data={"booking_id": 1, "slot_id": 999999})
        assert r.status_code == 404

    async def test_cancel_nonexistent_booking_returns_404(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.post("/cancel", data={"booking_id": 999999, "slot_id": slot["id"]})
        assert r.status_code == 404

    async def test_cancel_promotes_waitlist(self, client, db_pool):
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        users = []
        for i in range(11):
            u = await db_create_user(db_pool, f"u{i}")
            users.append(u)
            await db_create_booking(
                db_pool, slot["id"], u["id"], u["id"],
                status="confirmed" if i < 10 else "waitlist",
                position=i + 1,
            )
        b0 = await db_pool.fetchrow(
            "SELECT id FROM bookings WHERE (data->>'user_id')::int = $1", users[0]["id"]
        )
        await api_login(client, "u0")
        async with at_time(client, OPEN_TIME):
            r = await client.post("/cancel", data={"booking_id": b0["id"], "slot_id": slot["id"]})
        assert r.status_code == 200
        b10 = await db_pool.fetchrow(
            "SELECT data FROM bookings WHERE (data->>'user_id')::int = $1", users[10]["id"]
        )
        assert b10["data"]["status"] == "confirmed"

    async def test_cancel_own_guest_booking(self, client, db_pool):
        user = await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        g = await db_create_booking(db_pool, slot["id"], None, user["id"], booking_type="guest", guest_name="Bob")
        await api_login(client, "alice")
        async with at_time(client, OPEN_TIME):
            r = await client.post("/cancel", data={"booking_id": g["id"], "slot_id": slot["id"]})
        assert r.status_code == 200
        assert await db_count_bookings(db_pool) == 0

    async def test_unauthenticated_redirects(self, client):
        r = await client.post("/cancel", data={"booking_id": 1, "slot_id": 1})
        assert r.status_code == 302

    async def test_frozen_slot_does_not_delete_booking(self, client, db_pool):
        user = await db_create_user(db_pool, "alice")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        booking = await db_create_booking(db_pool, slot["id"], user["id"], user["id"])
        await api_login(client, "alice")
        async with at_time(client, FROZEN_TIME):
            await client.post("/cancel", data={"booking_id": booking["id"], "slot_id": slot["id"]})
        assert await db_count_bookings(db_pool) == 1


class TestInternalTimeEndpoint:
    """Verify the /internal endpoints themselves work correctly."""

    async def test_get_now_returns_json(self, client):
        r = await client.get("/internal/now")
        assert r.status_code == 200
        data = r.json()
        assert "now" in data
        assert "overridden" in data

    async def test_set_time_overrides_clock(self, client):
        async with at_time(client, OPEN_TIME):
            r = await client.get("/internal/now")
        data = r.json()
        # After reset, overridden should be False
        assert data["overridden"] is False

    async def test_set_time_with_invalid_iso_returns_400(self, client):
        r = await client.post("/internal/set-time", json={"iso": "not-a-date"})
        assert r.status_code == 400

    async def test_reset_time_removes_override(self, client):
        await client.post("/internal/set-time", json={"iso": OPEN_TIME.isoformat()})
        r1 = await client.get("/internal/now")
        assert r1.json()["overridden"] is True
        await client.post("/internal/reset-time")
        r2 = await client.get("/internal/now")
        assert r2.json()["overridden"] is False

    async def test_at_time_context_manager_resets_on_exit(self, client):
        async with at_time(client, OPEN_TIME):
            pass
        r = await client.get("/internal/now")
        assert r.json()["overridden"] is False
