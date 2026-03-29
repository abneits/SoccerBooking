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


class TestMainPage:
    async def test_unauthenticated_redirects_to_login(self, client):
        resp = await client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.headers["location"]

    async def test_authenticated_returns_200(self, client):
        await create_user("alice", "1234")
        await create_slot("2026-03-25")
        await login(client, "alice")
        resp = await client.get("/")
        assert resp.status_code == 200

    async def test_shows_slot_date(self, client):
        await create_user("alice", "1234")
        await create_slot("2026-03-25")
        await login(client, "alice")
        resp = await client.get("/")
        assert b"2026-03-25" in resp.content

    async def test_shows_no_slot_message_when_none(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        with patch("backend.routers.main._now") as mock_now:
            mock_now.return_value = datetime(2026, 3, 22, 10, tzinfo=TZ)  # Sunday
            resp = await client.get("/")
        assert resp.status_code == 200

    async def test_shows_cancelled_slot(self, client):
        await create_user("alice", "1234")
        await create_slot("2026-03-25", status="cancelled")
        await login(client, "alice")
        resp = await client.get("/")
        assert resp.status_code == 200

    async def test_shows_booking_list(self, client):
        user = await create_user("alice", "1234")
        slot = await create_slot("2026-03-25")
        await create_booking(slot["id"], user["id"], user["id"], "player")
        await login(client, "alice")
        resp = await client.get("/")
        assert b"alice" in resp.content

    async def test_admin_sees_admin_link(self, client):
        await create_user("admin", "1234", "admin")
        await create_slot("2026-03-25")
        await login(client, "admin")
        resp = await client.get("/")
        assert b"/admin" in resp.content

    async def test_player_does_not_see_admin_link(self, client):
        await create_user("alice", "1234", "player")
        await create_slot("2026-03-25")
        await login(client, "alice")
        resp = await client.get("/")
        assert b"Admin" not in resp.content


class TestBookEndpoint:
    async def test_book_own_spot_during_open(self, client):
        user = await create_user("alice", "1234")
        slot = await create_slot("2026-03-25")
        await login(client, "alice")
        with patch("backend.routers.main._now", return_value=OPEN_TIME):
            resp = await client.post(
                "/book", data={"slot_id": slot["id"], "type": "player"}
            )
        assert resp.status_code == 200
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 1

    async def test_book_returns_403_during_frozen(self, client):
        await create_user("alice", "1234")
        slot = await create_slot("2026-03-25")
        await login(client, "alice")
        with patch("backend.routers.main._now", return_value=FROZEN_TIME):
            resp = await client.post(
                "/book", data={"slot_id": slot["id"], "type": "player"}
            )
        assert resp.status_code == 403

    async def test_book_returns_403_during_closed(self, client):
        await create_user("alice", "1234")
        slot = await create_slot("2026-03-25")
        await login(client, "alice")
        with patch("backend.routers.main._now", return_value=CLOSED_TIME):
            resp = await client.post(
                "/book", data={"slot_id": slot["id"], "type": "player"}
            )
        assert resp.status_code == 403

    async def test_book_returns_403_on_cancelled_slot(self, client):
        await create_user("alice", "1234")
        slot = await create_slot("2026-03-25", status="cancelled")
        await login(client, "alice")
        with patch("backend.routers.main._now", return_value=OPEN_TIME):
            resp = await client.post(
                "/book", data={"slot_id": slot["id"], "type": "player"}
            )
        assert resp.status_code == 403

    async def test_book_nonexistent_slot_returns_404(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        with patch("backend.routers.main._now", return_value=OPEN_TIME):
            resp = await client.post(
                "/book", data={"slot_id": 9999, "type": "player"}
            )
        assert resp.status_code == 404

    async def test_book_guest_spot(self, client):
        await create_user("alice", "1234")
        slot = await create_slot("2026-03-25")
        await login(client, "alice")
        with patch("backend.routers.main._now", return_value=OPEN_TIME):
            resp = await client.post(
                "/book", data={"slot_id": slot["id"], "type": "guest", "guest_name": "Bob"}
            )
        assert resp.status_code == 200
        row = await db_module.fetch_one(
            "SELECT data FROM bookings WHERE data->>'type' = 'guest'"
        )
        assert row["data"]["guest_name"] == "Bob"

    async def test_duplicate_player_booking_returns_400(self, client):
        user = await create_user("alice", "1234")
        slot = await create_slot("2026-03-25")
        await create_booking(slot["id"], user["id"], user["id"], "player")
        await login(client, "alice")
        with patch("backend.routers.main._now", return_value=OPEN_TIME):
            resp = await client.post(
                "/book", data={"slot_id": slot["id"], "type": "player"}
            )
        assert resp.status_code == 400

    async def test_book_when_full_returns_400(self, client):
        slot = await create_slot("2026-03-25")
        for i in range(12):
            u = await create_user(f"u{i}")
            await create_booking(slot["id"], u["id"], u["id"], "player")
        overflow = await create_user("overflow")
        await login(client, "overflow")
        with patch("backend.routers.main._now", return_value=OPEN_TIME):
            resp = await client.post(
                "/book", data={"slot_id": slot["id"], "type": "player"}
            )
        assert resp.status_code == 400

    async def test_book_unauthenticated_redirects(self, client):
        slot = await create_slot("2026-03-25")
        resp = await client.post(
            "/book", data={"slot_id": slot["id"], "type": "player"}, follow_redirects=False
        )
        assert resp.status_code == 302

    async def test_book_returns_partial_html(self, client):
        await create_user("alice", "1234")
        slot = await create_slot("2026-03-25")
        await login(client, "alice")
        with patch("backend.routers.main._now", return_value=OPEN_TIME):
            resp = await client.post(
                "/book", data={"slot_id": slot["id"], "type": "player"}
            )
        assert resp.status_code == 200
        assert b"alice" in resp.content


class TestCancelEndpoint:
    async def test_cancel_own_booking_during_open(self, client):
        user = await create_user("alice", "1234")
        slot = await create_slot("2026-03-25")
        booking = await create_booking(slot["id"], user["id"], user["id"], "player")
        await login(client, "alice")
        with patch("backend.routers.main._now", return_value=OPEN_TIME):
            resp = await client.post(
                "/cancel", data={"booking_id": booking["id"], "slot_id": slot["id"]}
            )
        assert resp.status_code == 200
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 0

    async def test_cannot_cancel_another_players_booking(self, client):
        alice = await create_user("alice", "1234")
        bob = await create_user("bob", "1234")
        slot = await create_slot("2026-03-25")
        booking = await create_booking(slot["id"], bob["id"], bob["id"], "player")
        await login(client, "alice")
        with patch("backend.routers.main._now", return_value=OPEN_TIME):
            resp = await client.post(
                "/cancel", data={"booking_id": booking["id"], "slot_id": slot["id"]}
            )
        assert resp.status_code == 403
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 1

    async def test_cancel_returns_403_during_frozen(self, client):
        user = await create_user("alice", "1234")
        slot = await create_slot("2026-03-25")
        booking = await create_booking(slot["id"], user["id"], user["id"], "player")
        await login(client, "alice")
        with patch("backend.routers.main._now", return_value=FROZEN_TIME):
            resp = await client.post(
                "/cancel", data={"booking_id": booking["id"], "slot_id": slot["id"]}
            )
        assert resp.status_code == 403

    async def test_cancel_returns_403_during_closed(self, client):
        user = await create_user("alice", "1234")
        slot = await create_slot("2026-03-25")
        booking = await create_booking(slot["id"], user["id"], user["id"], "player")
        await login(client, "alice")
        with patch("backend.routers.main._now", return_value=CLOSED_TIME):
            resp = await client.post(
                "/cancel", data={"booking_id": booking["id"], "slot_id": slot["id"]}
            )
        assert resp.status_code == 403

    async def test_cancel_nonexistent_slot_returns_404(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        with patch("backend.routers.main._now", return_value=OPEN_TIME):
            resp = await client.post(
                "/cancel", data={"booking_id": 1, "slot_id": 9999}
            )
        assert resp.status_code == 404

    async def test_cancel_nonexistent_booking_returns_404(self, client):
        await create_user("alice", "1234")
        slot = await create_slot("2026-03-25")
        await login(client, "alice")
        with patch("backend.routers.main._now", return_value=OPEN_TIME):
            resp = await client.post(
                "/cancel", data={"booking_id": 9999, "slot_id": slot["id"]}
            )
        assert resp.status_code == 404

    async def test_cancel_promotes_waitlist(self, client):
        slot = await create_slot("2026-03-25")
        users = []
        for i in range(11):
            u = await create_user(f"u{i}")
            users.append(u)
            await create_booking(slot["id"], u["id"], u["id"], "player")
        # u0 is confirmed, u10 is waitlist
        b0 = await db_module.fetch_one(
            "SELECT id FROM bookings WHERE (data->>'user_id')::int = $1", users[0]["id"]
        )
        await login(client, "u0")
        with patch("backend.routers.main._now", return_value=OPEN_TIME):
            resp = await client.post(
                "/cancel", data={"booking_id": b0["id"], "slot_id": slot["id"]}
            )
        assert resp.status_code == 200
        # u10 should now be confirmed
        b10 = await db_module.fetch_one(
            "SELECT data FROM bookings WHERE (data->>'user_id')::int = $1", users[10]["id"]
        )
        assert b10["data"]["status"] == "confirmed"

    async def test_cancel_own_guest_booking(self, client):
        user = await create_user("alice", "1234")
        slot = await create_slot("2026-03-25")
        guest_booking = await create_booking(slot["id"], None, user["id"], "guest", "Bob")
        await login(client, "alice")
        with patch("backend.routers.main._now", return_value=OPEN_TIME):
            resp = await client.post(
                "/cancel", data={"booking_id": guest_booking["id"], "slot_id": slot["id"]}
            )
        assert resp.status_code == 200
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 0

    async def test_cancel_unauthenticated_redirects(self, client):
        resp = await client.post(
            "/cancel", data={"booking_id": 1, "slot_id": 1}, follow_redirects=False
        )
        assert resp.status_code == 302
