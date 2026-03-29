from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo

from tests.conftest import create_user, create_slot, login
from backend.booking_utils import create_booking
from backend import db as db_module

TZ = ZoneInfo("Europe/Paris")
OPEN_TIME = datetime(2026, 3, 23, 14, tzinfo=TZ)          # Monday 14:00 — OPEN
CLOSED_TIME = datetime(2026, 3, 25, 18, 30, tzinfo=TZ)    # Wednesday 18:30 — CLOSED
FROZEN_TIME = datetime(2026, 3, 25, 20, tzinfo=TZ)         # Wednesday 20:00 — FROZEN


class TestAdminAccess:
    async def test_unauthenticated_redirects_to_login(self, client):
        resp = await client.get("/admin", follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.headers["location"]

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

    async def test_admin_panel_shows_users(self, client):
        await create_user("admin", "1234", "admin")
        await create_user("bob", "1234")
        await login(client, "admin")
        resp = await client.get("/admin")
        assert b"bob" in resp.content

    async def test_admin_panel_shows_slots(self, client):
        await create_user("admin", "1234", "admin")
        await create_slot("2026-03-25")
        await login(client, "admin")
        resp = await client.get("/admin")
        assert b"2026-03-25" in resp.content


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

    async def test_cancel_slot_without_reason(self, client):
        await create_user("admin", "1234", "admin")
        slot = await create_slot("2026-03-25")
        await login(client, "admin")
        resp = await client.post(
            "/admin/slot/cancel",
            data={"slot_id": slot["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        row = await db_module.fetch_one("SELECT data FROM slots WHERE id = $1", slot["id"])
        assert row["data"]["status"] == "cancelled"

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
        assert row["data"]["cancelled_reason"] == "Easter"

    async def test_precancel_existing_slot_by_date_updates_it(self, client):
        await create_user("admin", "1234", "admin")
        slot = await create_slot("2026-03-25")
        await login(client, "admin")
        resp = await client.post(
            "/admin/slot/cancel",
            data={"date": "2026-03-25", "reason": "Rain"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        row = await db_module.fetch_one("SELECT data FROM slots WHERE id = $1", slot["id"])
        assert row["data"]["status"] == "cancelled"
        assert row["data"]["cancelled_reason"] == "Rain"

    async def test_non_admin_cannot_cancel_slot(self, client):
        await create_user("alice", "1234", "player")
        slot = await create_slot("2026-03-25")
        await login(client, "alice")
        resp = await client.post(
            "/admin/slot/cancel",
            data={"slot_id": slot["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 302  # redirect, not 303


class TestAdminBookingManagement:
    async def test_admin_can_cancel_any_booking_during_open(self, client):
        await create_user("admin", "1234", "admin")
        bob = await create_user("bob", "1234")
        slot = await create_slot("2026-03-25")
        booking = await create_booking(slot["id"], bob["id"], bob["id"], "player")
        await login(client, "admin")
        with patch("backend.routers.admin._now", return_value=OPEN_TIME):
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
        bob = await create_user("bob", "1234")
        slot = await create_slot("2026-03-25")
        booking = await create_booking(slot["id"], bob["id"], bob["id"], "player")
        await login(client, "admin")
        with patch("backend.routers.admin._now", return_value=CLOSED_TIME):
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
        bob = await create_user("bob", "1234")
        slot = await create_slot("2026-03-25")
        booking = await create_booking(slot["id"], bob["id"], bob["id"], "player")
        await login(client, "admin")
        with patch("backend.routers.admin._now", return_value=FROZEN_TIME):
            resp = await client.post(
                "/admin/booking/cancel",
                data={"booking_id": booking["id"], "slot_id": slot["id"]},
            )
        assert resp.status_code == 403

    async def test_admin_cancel_promotes_waitlist(self, client):
        await create_user("admin", "1234", "admin")
        slot = await create_slot("2026-03-25")
        users = []
        for i in range(11):
            u = await create_user(f"u{i}")
            users.append(u)
            await create_booking(slot["id"], u["id"], u["id"], "player")
        b0 = await db_module.fetch_one(
            "SELECT id FROM bookings WHERE (data->>'user_id')::int = $1", users[0]["id"]
        )
        await login(client, "admin")
        with patch("backend.routers.admin._now", return_value=OPEN_TIME):
            resp = await client.post(
                "/admin/booking/cancel",
                data={"booking_id": b0["id"], "slot_id": slot["id"]},
                follow_redirects=False,
            )
        assert resp.status_code == 303
        b10 = await db_module.fetch_one(
            "SELECT data FROM bookings WHERE (data->>'user_id')::int = $1", users[10]["id"]
        )
        assert b10["data"]["status"] == "confirmed"

    async def test_admin_cancel_nonexistent_slot_returns_404(self, client):
        await create_user("admin", "1234", "admin")
        await login(client, "admin")
        with patch("backend.routers.admin._now", return_value=OPEN_TIME):
            resp = await client.post(
                "/admin/booking/cancel",
                data={"booking_id": 1, "slot_id": 9999},
            )
        assert resp.status_code == 404

    async def test_admin_can_add_player_by_username(self, client):
        await create_user("admin", "1234", "admin")
        bob = await create_user("bob", "1234")
        slot = await create_slot("2026-03-25")
        await login(client, "admin")
        with patch("backend.routers.admin._now", return_value=OPEN_TIME):
            resp = await client.post(
                "/admin/booking/add",
                data={"slot_id": slot["id"], "username": "bob"},
                follow_redirects=False,
            )
        assert resp.status_code == 303
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 1

    async def test_admin_can_add_player_during_closed(self, client):
        await create_user("admin", "1234", "admin")
        await create_user("bob", "1234")
        slot = await create_slot("2026-03-25")
        await login(client, "admin")
        with patch("backend.routers.admin._now", return_value=CLOSED_TIME):
            resp = await client.post(
                "/admin/booking/add",
                data={"slot_id": slot["id"], "username": "bob"},
                follow_redirects=False,
            )
        assert resp.status_code == 303
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 1

    async def test_admin_cannot_add_player_during_frozen(self, client):
        await create_user("admin", "1234", "admin")
        await create_user("bob", "1234")
        slot = await create_slot("2026-03-25")
        await login(client, "admin")
        with patch("backend.routers.admin._now", return_value=FROZEN_TIME):
            resp = await client.post(
                "/admin/booking/add",
                data={"slot_id": slot["id"], "username": "bob"},
            )
        assert resp.status_code == 403

    async def test_admin_add_unknown_username_returns_404(self, client):
        await create_user("admin", "1234", "admin")
        slot = await create_slot("2026-03-25")
        await login(client, "admin")
        with patch("backend.routers.admin._now", return_value=OPEN_TIME):
            resp = await client.post(
                "/admin/booking/add",
                data={"slot_id": slot["id"], "username": "ghost"},
            )
        assert resp.status_code == 404

    async def test_admin_add_duplicate_player_returns_400(self, client):
        await create_user("admin", "1234", "admin")
        bob = await create_user("bob", "1234")
        slot = await create_slot("2026-03-25")
        await create_booking(slot["id"], bob["id"], bob["id"], "player")
        await login(client, "admin")
        with patch("backend.routers.admin._now", return_value=OPEN_TIME):
            resp = await client.post(
                "/admin/booking/add",
                data={"slot_id": slot["id"], "username": "bob"},
            )
        assert resp.status_code == 400

    async def test_admin_add_to_nonexistent_slot_returns_404(self, client):
        await create_user("admin", "1234", "admin")
        await create_user("bob", "1234")
        await login(client, "admin")
        with patch("backend.routers.admin._now", return_value=OPEN_TIME):
            resp = await client.post(
                "/admin/booking/add",
                data={"slot_id": 9999, "username": "bob"},
            )
        assert resp.status_code == 404


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

    async def test_reset_pin_invalid_format_returns_400(self, client):
        await create_user("admin", "1234", "admin")
        bob = await create_user("bob", "1234")
        await login(client, "admin")
        resp = await client.post(
            "/admin/user/reset-pin",
            data={"user_id": bob["id"], "new_pin": "ab"},
        )
        assert resp.status_code == 400

    async def test_reset_pin_nonexistent_user_returns_404(self, client):
        await create_user("admin", "1234", "admin")
        await login(client, "admin")
        resp = await client.post(
            "/admin/user/reset-pin",
            data={"user_id": 9999, "new_pin": "5678"},
        )
        assert resp.status_code == 404

    async def test_delete_user(self, client):
        await create_user("admin", "1234", "admin")
        bob = await create_user("bob", "1234")
        await login(client, "admin")
        resp = await client.post(
            "/admin/user/delete",
            data={"user_id": bob["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        row = await db_module.fetch_one("SELECT id FROM users WHERE id = $1", bob["id"])
        assert row is None

    async def test_delete_user_cascades_open_slot_bookings(self, client):
        await create_user("admin", "1234", "admin")
        bob = await create_user("bob", "1234")
        slot = await create_slot("2026-03-25")
        await create_booking(slot["id"], bob["id"], bob["id"], "player")
        await login(client, "admin")
        resp = await client.post(
            "/admin/user/delete",
            data={"user_id": bob["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        booking_count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert booking_count == 0

    async def test_delete_user_promotes_waitlist_on_cascade(self, client):
        await create_user("admin", "1234", "admin")
        slot = await create_slot("2026-03-25")
        users = []
        for i in range(11):
            u = await create_user(f"u{i}")
            users.append(u)
            await create_booking(slot["id"], u["id"], u["id"], "player")
        # u10 is on waitlist, delete u0 should promote u10
        await login(client, "admin")
        resp = await client.post(
            "/admin/user/delete",
            data={"user_id": users[0]["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        b10 = await db_module.fetch_one(
            "SELECT data FROM bookings WHERE (data->>'user_id')::int = $1", users[10]["id"]
        )
        assert b10["data"]["status"] == "confirmed"

    async def test_delete_user_does_not_cascade_cancelled_slot_bookings(self, client):
        await create_user("admin", "1234", "admin")
        bob = await create_user("bob", "1234")
        slot = await create_slot("2026-03-25", status="cancelled")
        await create_booking(slot["id"], bob["id"], bob["id"], "player")
        await login(client, "admin")
        resp = await client.post(
            "/admin/user/delete",
            data={"user_id": bob["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        # Booking on cancelled slot should remain (not cascaded)
        booking_count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert booking_count == 1

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

    async def test_demote_to_player(self, client):
        await create_user("admin", "1234", "admin")
        bob = await create_user("bob", "1234", "admin")
        await login(client, "admin")
        resp = await client.post(
            "/admin/user/set-role",
            data={"user_id": bob["id"], "role": "player"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        row = await db_module.fetch_one("SELECT data FROM users WHERE id = $1", bob["id"])
        assert row["data"]["role"] == "player"

    async def test_set_invalid_role_returns_400(self, client):
        await create_user("admin", "1234", "admin")
        bob = await create_user("bob", "1234")
        await login(client, "admin")
        resp = await client.post(
            "/admin/user/set-role",
            data={"user_id": bob["id"], "role": "superadmin"},
        )
        assert resp.status_code == 400

    async def test_set_role_nonexistent_user_returns_404(self, client):
        await create_user("admin", "1234", "admin")
        await login(client, "admin")
        resp = await client.post(
            "/admin/user/set-role",
            data={"user_id": 9999, "role": "admin"},
        )
        assert resp.status_code == 404

    async def test_delete_guest_bookings_on_user_delete(self, client):
        await create_user("admin", "1234", "admin")
        bob = await create_user("bob", "1234")
        slot = await create_slot("2026-03-25")
        await create_booking(slot["id"], None, bob["id"], "guest", "Guest1")
        await login(client, "admin")
        resp = await client.post(
            "/admin/user/delete",
            data={"user_id": bob["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        booking_count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert booking_count == 0
