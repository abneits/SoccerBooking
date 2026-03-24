import pytest
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo

from tests.conftest import create_user, create_slot, login
from backend.booking_utils import create_booking
from backend import db as db_module

TZ = ZoneInfo("Europe/Paris")
OPEN_TIME   = datetime(2026, 3, 23, 14, tzinfo=TZ)       # Monday 14:00 — OPEN
CLOSED_TIME = datetime(2026, 3, 25, 18, 30, tzinfo=TZ)   # Wednesday 18:30 — CLOSED
FROZEN_TIME = datetime(2026, 3, 25, 20, tzinfo=TZ)        # Wednesday 20:00 — FROZEN


class TestAdminAccess:
    async def test_non_admin_redirected_to_home(self, client):
        await create_user("alice", "1234", "player")
        await login(client, "alice")
        resp = await client.get("/admin", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"

    async def test_admin_can_access_panel(self, client):
        await create_user("admin", "1234", "admin")
        await login(client, "admin")
        resp = await client.get("/admin")
        assert resp.status_code == 200


class TestAdminSlotManagement:
    async def test_cancel_existing_slot(self, client):
        await create_user("admin", "1234", "admin")
        slot = await create_slot("2026-03-25")
        await login(client, "admin")
        resp = await client.post(
            "/admin/slot/cancel",
            data={"slot_id": slot["id"], "reason": "Holiday"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        row = await db_module.fetch_one("SELECT data FROM slots WHERE id = $1", slot["id"])
        assert row["data"]["status"] == "cancelled"
        assert row["data"]["cancelled_reason"] == "Holiday"

    async def test_precancel_future_slot_by_date_creates_row(self, client):
        await create_user("admin", "1234", "admin")
        await login(client, "admin")
        resp = await client.post(
            "/admin/slot/cancel",
            data={"date": "2026-04-01", "reason": "Easter"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        row = await db_module.fetch_one("SELECT data FROM slots WHERE data->>'date' = '2026-04-01'")
        assert row is not None
        assert row["data"]["status"] == "cancelled"


class TestAdminBookingManagement:
    async def test_admin_can_cancel_any_booking_during_open(self, client):
        await create_user("admin", "1234", "admin")
        bob  = await create_user("bob", "1234")
        slot = await create_slot("2026-03-25")
        booking = await create_booking(slot["id"], bob["id"], bob["id"], "player")
        await login(client, "admin")
        with patch("backend.routers.admin.datetime") as mock_dt:
            mock_dt.now.return_value = OPEN_TIME
            resp = await client.post(
                "/admin/booking/cancel",
                data={"booking_id": booking["id"], "slot_id": slot["id"]},
                follow_redirects=False,
            )
        assert resp.status_code == 303
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 0

    async def test_admin_can_cancel_during_closed(self, client):
        await create_user("admin", "1234", "admin")
        bob  = await create_user("bob", "1234")
        slot = await create_slot("2026-03-25")
        booking = await create_booking(slot["id"], bob["id"], bob["id"], "player")
        await login(client, "admin")
        with patch("backend.routers.admin.datetime") as mock_dt:
            mock_dt.now.return_value = CLOSED_TIME
            resp = await client.post(
                "/admin/booking/cancel",
                data={"booking_id": booking["id"], "slot_id": slot["id"]},
                follow_redirects=False,
            )
        assert resp.status_code == 303
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 0

    async def test_admin_cannot_cancel_during_frozen(self, client):
        await create_user("admin", "1234", "admin")
        bob  = await create_user("bob", "1234")
        slot = await create_slot("2026-03-25")
        booking = await create_booking(slot["id"], bob["id"], bob["id"], "player")
        await login(client, "admin")
        with patch("backend.routers.admin.datetime") as mock_dt:
            mock_dt.now.return_value = FROZEN_TIME
            resp = await client.post(
                "/admin/booking/cancel",
                data={"booking_id": booking["id"], "slot_id": slot["id"]},
            )
        assert resp.status_code == 403

    async def test_admin_can_add_player_by_username(self, client):
        await create_user("admin", "1234", "admin")
        bob  = await create_user("bob", "1234")
        slot = await create_slot("2026-03-25")
        await login(client, "admin")
        with patch("backend.routers.admin.datetime") as mock_dt:
            mock_dt.now.return_value = OPEN_TIME
            resp = await client.post(
                "/admin/booking/add",
                data={"slot_id": slot["id"], "username": "bob"},
                follow_redirects=False,
            )
        assert resp.status_code == 303
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 1


class TestAdminUserManagement:
    async def test_reset_pin(self, client):
        await create_user("admin", "1234", "admin")
        bob = await create_user("bob", "1234")
        await login(client, "admin")
        resp = await client.post(
            "/admin/user/reset-pin",
            data={"user_id": bob["id"], "new_pin": "5678"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        row = await db_module.fetch_one("SELECT data FROM users WHERE id = $1", bob["id"])
        assert row["data"]["pin"] == "5678"

    async def test_delete_user_cascades_open_slot_bookings(self, client):
        await create_user("admin", "1234", "admin")
        bob  = await create_user("bob", "1234")
        slot = await create_slot("2026-03-25")
        await create_booking(slot["id"], bob["id"], bob["id"], "player")
        await login(client, "admin")
        resp = await client.post(
            "/admin/user/delete",
            data={"user_id": bob["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        user_row = await db_module.fetch_one("SELECT id FROM users WHERE id = $1", bob["id"])
        assert user_row is None
        booking_count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert booking_count == 0

    async def test_promote_to_admin(self, client):
        await create_user("admin", "1234", "admin")
        bob = await create_user("bob", "1234")
        await login(client, "admin")
        resp = await client.post(
            "/admin/user/set-role",
            data={"user_id": bob["id"], "role": "admin"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        row = await db_module.fetch_one("SELECT data FROM users WHERE id = $1", bob["id"])
        assert row["data"]["role"] == "admin"
