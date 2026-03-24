import pytest
from tests.conftest import create_user, login
from backend import db as db_module


class TestRegister:
    async def test_get_register_returns_200(self, client):
        resp = await client.get("/register")
        assert resp.status_code == 200

    async def test_register_creates_user_and_redirects(self, client):
        resp = await client.post(
            "/register", data={"username": "alice", "pin": "1234"}, follow_redirects=False
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"
        row = await db_module.fetch_one("SELECT data FROM users WHERE data->>'username' = 'alice'")
        assert row is not None

    async def test_register_duplicate_username_shows_error(self, client):
        await create_user("alice")
        resp = await client.post("/register", data={"username": "alice", "pin": "1234"})
        assert resp.status_code == 400
        assert b"taken" in resp.content.lower()

    async def test_register_short_pin_shows_error(self, client):
        resp = await client.post("/register", data={"username": "bob", "pin": "12"})
        assert resp.status_code == 400
        assert b"digit" in resp.content.lower() or b"4" in resp.content


class TestLogin:
    async def test_login_success_redirects_to_home(self, client):
        await create_user("alice", "1234")
        resp = await client.post(
            "/login", data={"username": "alice", "pin": "1234"}, follow_redirects=False
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"

    async def test_login_wrong_pin_shows_error(self, client):
        await create_user("alice", "1234")
        resp = await client.post("/login", data={"username": "alice", "pin": "9999"})
        assert resp.status_code == 401
        assert b"invalid" in resp.content.lower()

    async def test_login_unknown_user_shows_error(self, client):
        resp = await client.post("/login", data={"username": "nobody", "pin": "1234"})
        assert resp.status_code == 401
        assert b"invalid" in resp.content.lower()


class TestLogout:
    async def test_logout_clears_session_and_redirects(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")

        resp = await client.get("/logout", follow_redirects=False)
        assert resp.status_code == 303

        # After logout, / must redirect to /login
        resp2 = await client.get("/", follow_redirects=False)
        assert resp2.status_code == 302
        assert "login" in resp2.headers["location"]
