import pytest
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo

from tests.conftest import create_user, create_slot, login
from backend.booking_utils import create_booking
from backend import db as db_module

TZ = ZoneInfo("Europe/Paris")
OPEN_TIME   = datetime(2026, 3, 23, 14, tzinfo=TZ)   # Monday 14:00 — OPEN
FROZEN_TIME = datetime(2026, 3, 25, 20, tzinfo=TZ)   # Wednesday 20:00 — FROZEN
CLOSED_TIME = datetime(2026, 3, 25, 18, 30, tzinfo=TZ)  # Wednesday 18:30 — CLOSED


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


class TestBookEndpoint:
    async def test_book_own_spot_during_open(self, client):
        user = await create_user("alice", "1234")
        slot = await create_slot("2026-03-25")
        await login(client, "alice")
        with patch("backend.routers.main.datetime") as mock_dt:
            mock_dt.now.return_value = OPEN_TIME
            resp = await client.post(
                "/book", data={"slot_id": slot["id"], "type": "player"}
            )
        assert resp.status_code == 200
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 1

    async def test_book_returns_403_during_frozen(self, client):
        user = await create_user("alice", "1234")
        slot = await create_slot("2026-03-25")
        await login(client, "alice")
        with patch("backend.routers.main.datetime") as mock_dt:
            mock_dt.now.return_value = FROZEN_TIME
            resp = await client.post(
                "/book", data={"slot_id": slot["id"], "type": "player"}
            )
        assert resp.status_code == 403

    async def test_cancel_own_booking_during_open(self, client):
        user = await create_user("alice", "1234")
        slot = await create_slot("2026-03-25")
        booking = await create_booking(slot["id"], user["id"], user["id"], "player")
        await login(client, "alice")
        with patch("backend.routers.main.datetime") as mock_dt:
            mock_dt.now.return_value = OPEN_TIME
            resp = await client.post(
                "/cancel", data={"booking_id": booking["id"], "slot_id": slot["id"]}
            )
        assert resp.status_code == 200
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 0

    async def test_cannot_cancel_another_players_booking(self, client):
        alice = await create_user("alice", "1234")
        bob   = await create_user("bob", "1234")
        slot  = await create_slot("2026-03-25")
        booking = await create_booking(slot["id"], bob["id"], bob["id"], "player")
        await login(client, "alice")
        with patch("backend.routers.main.datetime") as mock_dt:
            mock_dt.now.return_value = OPEN_TIME
            resp = await client.post(
                "/cancel", data={"booking_id": booking["id"], "slot_id": slot["id"]}
            )
        assert resp.status_code == 403
