import pytest
from tests.conftest import create_user, login
from backend import db as db_module


class TestProfilePage:
    async def test_unauthenticated_redirects(self, client):
        resp = await client.get("/profile", follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.headers["location"]

    async def test_authenticated_returns_200(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.get("/profile")
        assert resp.status_code == 200

    async def test_change_pin_success(self, client):
        user = await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "5678", "confirm_pin": "5678"},
        )
        assert resp.status_code == 200
        row = await db_module.fetch_one("SELECT data FROM users WHERE id = $1", user["id"])
        assert row["data"]["pin"] == "5678"

    async def test_wrong_current_pin_shows_error(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.post(
            "/profile/pin",
            data={"current_pin": "9999", "new_pin": "5678", "confirm_pin": "5678"},
        )
        assert resp.status_code == 400
        assert (
            b"incorrect" in resp.content.lower()
            or b"invalid" in resp.content.lower()
            or b"wrong" in resp.content.lower()
        )

    async def test_pin_mismatch_shows_error(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "5678", "confirm_pin": "9999"},
        )
        assert resp.status_code == 400
        assert b"match" in resp.content.lower()

    async def test_new_pin_must_be_4_digits(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "12", "confirm_pin": "12"},
        )
        assert resp.status_code == 400
        assert b"4" in resp.content or b"digit" in resp.content.lower()
