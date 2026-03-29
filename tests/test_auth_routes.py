from tests.conftest import create_user, login
from backend import db as db_module


class TestRegisterGet:
    async def test_returns_200(self, client):
        resp = await client.get("/register")
        assert resp.status_code == 200

    async def test_contains_form(self, client):
        resp = await client.get("/register")
        assert b"<form" in resp.content
        assert b"/register" in resp.content


class TestRegisterPost:
    async def test_creates_user_and_redirects_to_login(self, client):
        resp = await client.post(
            "/register", data={"username": "alice", "pin": "1234"}, follow_redirects=False
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"
        row = await db_module.fetch_one("SELECT data FROM users WHERE data->>'username' = 'alice'")
        assert row is not None
        assert row["data"]["pin"] == "1234"
        assert row["data"]["role"] == "player"

    async def test_duplicate_username_returns_400(self, client):
        await create_user("alice")
        resp = await client.post("/register", data={"username": "alice", "pin": "1234"})
        assert resp.status_code == 400

    async def test_short_pin_returns_400(self, client):
        resp = await client.post("/register", data={"username": "bob", "pin": "12"})
        assert resp.status_code == 400

    async def test_non_numeric_pin_returns_400(self, client):
        resp = await client.post("/register", data={"username": "bob", "pin": "abcd"})
        assert resp.status_code == 400

    async def test_empty_username_returns_400(self, client):
        resp = await client.post("/register", data={"username": "   ", "pin": "1234"})
        assert resp.status_code == 400

    async def test_5_digit_pin_returns_400(self, client):
        resp = await client.post("/register", data={"username": "bob", "pin": "12345"})
        assert resp.status_code == 400

    async def test_strips_username_whitespace(self, client):
        resp = await client.post(
            "/register", data={"username": "  alice  ", "pin": "1234"}, follow_redirects=False
        )
        assert resp.status_code == 303
        row = await db_module.fetch_one("SELECT data FROM users WHERE data->>'username' = 'alice'")
        assert row is not None


class TestLoginGet:
    async def test_returns_200(self, client):
        resp = await client.get("/login")
        assert resp.status_code == 200

    async def test_contains_form(self, client):
        resp = await client.get("/login")
        assert b"<form" in resp.content


class TestLoginPost:
    async def test_success_redirects_to_home(self, client):
        await create_user("alice", "1234")
        resp = await client.post(
            "/login", data={"username": "alice", "pin": "1234"}, follow_redirects=False
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"

    async def test_sets_session_cookie(self, client):
        await create_user("alice", "1234")
        resp = await client.post(
            "/login", data={"username": "alice", "pin": "1234"}, follow_redirects=False
        )
        assert "session" in resp.headers.get("set-cookie", "").lower()

    async def test_wrong_pin_returns_401(self, client):
        await create_user("alice", "1234")
        resp = await client.post("/login", data={"username": "alice", "pin": "9999"})
        assert resp.status_code == 401

    async def test_unknown_user_returns_401(self, client):
        resp = await client.post("/login", data={"username": "nobody", "pin": "1234"})
        assert resp.status_code == 401

    async def test_after_login_can_access_home(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.get("/", follow_redirects=False)
        assert resp.status_code == 200


class TestLogout:
    async def test_redirects_to_login(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.get("/logout", follow_redirects=False)
        assert resp.status_code == 303
        assert "login" in resp.headers["location"]

    async def test_clears_session(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        await client.get("/logout", follow_redirects=False)
        resp = await client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.headers["location"]

    async def test_logout_without_session_still_redirects(self, client):
        resp = await client.get("/logout", follow_redirects=False)
        assert resp.status_code == 303
