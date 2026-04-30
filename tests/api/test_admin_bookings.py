"""
API tests — Admin: booking management
Covers POST /admin/booking/cancel and POST /admin/booking/add.
Uses at_time() for full state coverage: OPEN, CLOSED, FROZEN, CANCELLED.
"""

import pytest
from tests.helpers import (
    db_create_user,
    db_create_slot,
    db_create_booking,
    db_fill_slot,
    db_count_bookings,
    db_fetch_bookings,
    api_login,
    at_time,
    TEST_WEDNESDAY,
    OPEN_TIME,
    CLOSED_TIME,
    FROZEN_TIME,
)


class TestAdminCancelBooking:
    async def test_can_cancel_during_open(self, admin_client, db_pool):
        bob = await db_create_user(db_pool, "bob")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        booking = await db_create_booking(db_pool, slot["id"], bob["id"], bob["id"])
        async with at_time(admin_client, OPEN_TIME):
            r = await admin_client.post(
                "/admin/booking/cancel",
                data={"booking_id": booking["id"], "slot_id": slot["id"]},
            )
        assert r.status_code == 303
        assert await db_count_bookings(db_pool) == 0

    async def test_can_cancel_during_closed(self, admin_client, db_pool):
        bob = await db_create_user(db_pool, "bob")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        booking = await db_create_booking(db_pool, slot["id"], bob["id"], bob["id"])
        async with at_time(admin_client, CLOSED_TIME):
            r = await admin_client.post(
                "/admin/booking/cancel",
                data={"booking_id": booking["id"], "slot_id": slot["id"]},
            )
        assert r.status_code == 303
        assert await db_count_bookings(db_pool) == 0

    async def test_cannot_cancel_during_frozen(self, admin_client, db_pool):
        bob = await db_create_user(db_pool, "bob")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        booking = await db_create_booking(db_pool, slot["id"], bob["id"], bob["id"])
        async with at_time(admin_client, FROZEN_TIME):
            r = await admin_client.post(
                "/admin/booking/cancel",
                data={"booking_id": booking["id"], "slot_id": slot["id"]},
            )
        assert r.status_code == 403
        assert await db_count_bookings(db_pool) == 1

    async def test_cannot_cancel_on_cancelled_slot(self, admin_client, db_pool):
        bob = await db_create_user(db_pool, "bob")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY, status="cancelled")
        booking = await db_create_booking(db_pool, slot["id"], bob["id"], bob["id"])
        async with at_time(admin_client, OPEN_TIME):
            r = await admin_client.post(
                "/admin/booking/cancel",
                data={"booking_id": booking["id"], "slot_id": slot["id"]},
            )
        assert r.status_code == 403

    async def test_nonexistent_slot_returns_404(self, admin_client):
        async with at_time(admin_client, OPEN_TIME):
            r = await admin_client.post(
                "/admin/booking/cancel",
                data={"booking_id": 1, "slot_id": 999999},
            )
        assert r.status_code == 404

    async def test_cancel_promotes_waitlist_during_open(self, admin_client, db_pool):
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        users = [await db_create_user(db_pool, f"u{i}") for i in range(11)]
        bookings = []
        for i in range(10):
            b = await db_create_booking(
                db_pool, slot["id"], users[i]["id"], users[i]["id"],
                status="confirmed", position=i + 1,
            )
            bookings.append(b)
        wl = await db_create_booking(
            db_pool, slot["id"], users[10]["id"], users[10]["id"],
            status="waitlist", position=11,
        )
        async with at_time(admin_client, OPEN_TIME):
            r = await admin_client.post(
                "/admin/booking/cancel",
                data={"booking_id": bookings[0]["id"], "slot_id": slot["id"]},
            )
        assert r.status_code == 303
        row = await db_pool.fetchrow("SELECT data FROM bookings WHERE id = $1", wl["id"])
        assert row["data"]["status"] == "confirmed"

    async def test_cancel_promotes_waitlist_during_closed(self, admin_client, db_pool):
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        users = [await db_create_user(db_pool, f"c{i}") for i in range(11)]
        bookings = []
        for i in range(10):
            b = await db_create_booking(
                db_pool, slot["id"], users[i]["id"], users[i]["id"],
                status="confirmed", position=i + 1,
            )
            bookings.append(b)
        wl = await db_create_booking(
            db_pool, slot["id"], users[10]["id"], users[10]["id"],
            status="waitlist", position=11,
        )
        async with at_time(admin_client, CLOSED_TIME):
            r = await admin_client.post(
                "/admin/booking/cancel",
                data={"booking_id": bookings[0]["id"], "slot_id": slot["id"]},
            )
        assert r.status_code == 303
        row = await db_pool.fetchrow("SELECT data FROM bookings WHERE id = $1", wl["id"])
        assert row["data"]["status"] == "confirmed"

    async def test_redirect_goes_to_admin(self, admin_client, db_pool):
        bob = await db_create_user(db_pool, "bob")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        booking = await db_create_booking(db_pool, slot["id"], bob["id"], bob["id"])
        async with at_time(admin_client, OPEN_TIME):
            r = await admin_client.post(
                "/admin/booking/cancel",
                data={"booking_id": booking["id"], "slot_id": slot["id"]},
            )
        assert r.headers["location"] == "/admin"

    async def test_non_admin_cannot_cancel(self, player_client, db_pool):
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        r = await player_client.post(
            "/admin/booking/cancel",
            data={"booking_id": 1, "slot_id": slot["id"]},
        )
        assert r.status_code == 302

    async def test_unauthenticated_cannot_cancel(self, client, db_pool):
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        r = await client.post(
            "/admin/booking/cancel",
            data={"booking_id": 1, "slot_id": slot["id"]},
        )
        assert r.status_code == 302


class TestAdminAddBooking:
    async def test_can_add_player_during_open(self, admin_client, db_pool):
        bob = await db_create_user(db_pool, "bob")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        async with at_time(admin_client, OPEN_TIME):
            r = await admin_client.post(
                "/admin/booking/add",
                data={"slot_id": slot["id"], "username": "bob"},
            )
        assert r.status_code == 303
        assert await db_count_bookings(db_pool) == 1

    async def test_can_add_player_during_closed(self, admin_client, db_pool):
        bob = await db_create_user(db_pool, "bob")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        async with at_time(admin_client, CLOSED_TIME):
            r = await admin_client.post(
                "/admin/booking/add",
                data={"slot_id": slot["id"], "username": "bob"},
            )
        assert r.status_code == 303
        assert await db_count_bookings(db_pool) == 1

    async def test_cannot_add_during_frozen(self, admin_client, db_pool):
        await db_create_user(db_pool, "bob")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        async with at_time(admin_client, FROZEN_TIME):
            r = await admin_client.post(
                "/admin/booking/add",
                data={"slot_id": slot["id"], "username": "bob"},
            )
        assert r.status_code == 403

    async def test_cannot_add_on_cancelled_slot(self, admin_client, db_pool):
        await db_create_user(db_pool, "bob")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY, status="cancelled")
        async with at_time(admin_client, OPEN_TIME):
            r = await admin_client.post(
                "/admin/booking/add",
                data={"slot_id": slot["id"], "username": "bob"},
            )
        assert r.status_code == 403

    async def test_unknown_username_returns_404(self, admin_client, db_pool):
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        async with at_time(admin_client, OPEN_TIME):
            r = await admin_client.post(
                "/admin/booking/add",
                data={"slot_id": slot["id"], "username": "ghost_xyz_qqq"},
            )
        assert r.status_code == 404

    async def test_nonexistent_slot_returns_404(self, admin_client, db_pool):
        await db_create_user(db_pool, "bob")
        async with at_time(admin_client, OPEN_TIME):
            r = await admin_client.post(
                "/admin/booking/add",
                data={"slot_id": 999999, "username": "bob"},
            )
        assert r.status_code == 404

    async def test_duplicate_player_returns_400(self, admin_client, db_pool):
        bob = await db_create_user(db_pool, "bob")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        await db_create_booking(db_pool, slot["id"], bob["id"], bob["id"])
        async with at_time(admin_client, OPEN_TIME):
            r = await admin_client.post(
                "/admin/booking/add",
                data={"slot_id": slot["id"], "username": "bob"},
            )
        assert r.status_code == 400

    async def test_added_booking_booked_by_id_is_admin(self, admin_client, db_pool):
        bob = await db_create_user(db_pool, "bob")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        async with at_time(admin_client, OPEN_TIME):
            await admin_client.post(
                "/admin/booking/add",
                data={"slot_id": slot["id"], "username": "bob"},
            )
        all_b = await db_fetch_bookings(db_pool, slot["id"])
        assert len(all_b) == 1
        assert all_b[0]["user_id"] == bob["id"]
        # booked_by_id should be the admin (testadmin), not bob
        assert all_b[0]["booked_by_id"] != bob["id"]

    async def test_add_goes_to_waitlist_when_confirmed_full(self, admin_client, db_pool):
        await db_create_user(db_pool, "bob")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        await db_fill_slot(db_pool, slot["id"], confirmed=10)
        async with at_time(admin_client, OPEN_TIME):
            r = await admin_client.post(
                "/admin/booking/add",
                data={"slot_id": slot["id"], "username": "bob"},
            )
        assert r.status_code == 303
        all_b = await db_fetch_bookings(db_pool, slot["id"])
        bob_booking = next(b for b in all_b if b["user_id"] is not None and
                          await db_pool.fetchval(
                              "SELECT data->>'username' FROM users WHERE id = $1", b["user_id"]
                          ) == "bob")
        assert bob_booking["status"] == "waitlist"

    async def test_non_admin_cannot_add(self, player_client, db_pool):
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        r = await player_client.post(
            "/admin/booking/add",
            data={"slot_id": slot["id"], "username": "someone"},
        )
        assert r.status_code == 302

    async def test_redirect_goes_to_admin(self, admin_client, db_pool):
        await db_create_user(db_pool, "bob")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        async with at_time(admin_client, OPEN_TIME):
            r = await admin_client.post(
                "/admin/booking/add",
                data={"slot_id": slot["id"], "username": "bob"},
            )
        assert r.headers["location"] == "/admin"
