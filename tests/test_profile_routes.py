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

    async def test_shows_username(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.get("/profile")
        assert b"alice" in resp.content

    async def test_shows_admin_badge_for_admin(self, client):
        await create_user("boss", "1234", "admin")
        await login(client, "boss")
        resp = await client.get("/profile")
        assert b"admin" in resp.content


class TestChangePinSuccess:
    async def test_updates_pin_in_db(self, client):
        user = await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "5678", "confirm_pin": "5678"},
        )
        assert resp.status_code == 200
        row = await db_module.fetch_one("SELECT data FROM users WHERE id = $1", user["id"])
        assert row["data"]["pin"] == "5678"

    async def test_can_login_with_new_pin(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "5678", "confirm_pin": "5678"},
        )
        await client.get("/logout")
        resp = await client.post(
            "/login", data={"username": "alice", "pin": "5678"}, follow_redirects=False
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"

    async def test_old_pin_no_longer_works(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "5678", "confirm_pin": "5678"},
        )
        await client.get("/logout")
        resp = await client.post("/login", data={"username": "alice", "pin": "1234"})
        assert resp.status_code == 401


class TestChangePinErrors:
    async def test_wrong_current_pin(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.post(
            "/profile/pin",
            data={"current_pin": "9999", "new_pin": "5678", "confirm_pin": "5678"},
        )
        assert resp.status_code == 400

    async def test_pin_mismatch(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "5678", "confirm_pin": "9999"},
        )
        assert resp.status_code == 400

    async def test_new_pin_too_short(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "12", "confirm_pin": "12"},
        )
        assert resp.status_code == 400

    async def test_new_pin_too_long(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "12345", "confirm_pin": "12345"},
        )
        assert resp.status_code == 400

    async def test_non_numeric_new_pin(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "abcd", "confirm_pin": "abcd"},
        )
        assert resp.status_code == 400

    async def test_unauthenticated_pin_change_redirects(self, client):
        resp = await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "5678", "confirm_pin": "5678"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
