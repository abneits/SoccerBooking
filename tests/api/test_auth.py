"""
API tests — Authentication
Covers: GET/POST /register, GET/POST /login, GET /logout, session lifecycle.
"""

import pytest
from tests.helpers import db_create_user, api_login, api_register, decode_data


class TestRegisterPage:
    async def test_get_returns_200(self, client):
        r = await client.get("/register")
        assert r.status_code == 200

    async def test_get_contains_form(self, client):
        r = await client.get("/register")
        assert b"<form" in r.content
        assert b"/register" in r.content

    async def test_get_has_username_and_pin_fields(self, client):
        r = await client.get("/register")
        assert b'name="username"' in r.content
        assert b'name="pin"' in r.content


class TestRegisterPost:
    async def test_success_redirects_to_login(self, client):
        r = await api_register(client, "alice", "1234")
        assert r.status_code == 303
        assert r.headers["location"] == "/login"

    async def test_creates_user_in_db(self, client, db_pool):
        await api_register(client, "alice", "1234")
        row = await db_pool.fetchrow(
            "SELECT data FROM users WHERE data->>'username' = 'alice'"
        )
        assert row is not None
        assert decode_data(row)["pin"] == "1234"
        assert decode_data(row)["role"] == "player"

    async def test_strips_whitespace_from_username(self, client, db_pool):
        r = await api_register(client, "  alice  ", "1234")
        assert r.status_code == 303
        row = await db_pool.fetchrow(
            "SELECT id FROM users WHERE data->>'username' = 'alice'"
        )
        assert row is not None

    async def test_duplicate_username_returns_400(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        r = await api_register(client, "alice", "5678")
        assert r.status_code == 400

    async def test_duplicate_is_case_sensitive(self, client, db_pool):
        """'Alice' and 'alice' are different users."""
        await db_create_user(db_pool, "alice")
        r = await api_register(client, "Alice", "5678")
        assert r.status_code == 303

    async def test_empty_username_returns_400(self, client):
        r = await api_register(client, "", "1234")
        assert r.status_code == 400

    async def test_whitespace_only_username_returns_400(self, client):
        r = await api_register(client, "   ", "1234")
        assert r.status_code == 400

    async def test_pin_too_short_returns_400(self, client):
        r = await api_register(client, "bob", "123")
        assert r.status_code == 400

    async def test_pin_too_long_returns_400(self, client):
        r = await api_register(client, "bob", "12345")
        assert r.status_code == 400

    async def test_pin_non_numeric_returns_400(self, client):
        r = await api_register(client, "bob", "abcd")
        assert r.status_code == 400

    async def test_pin_alphanumeric_mixed_returns_400(self, client):
        r = await api_register(client, "bob", "12ab")
        assert r.status_code == 400

    async def test_pin_with_spaces_returns_400(self, client):
        r = await api_register(client, "bob", "12 4")
        assert r.status_code == 400

    async def test_pin_zero_padded_is_valid(self, client):
        """'0001' is 4 digits and valid."""
        r = await api_register(client, "bob", "0001")
        assert r.status_code == 303

    async def test_pin_all_zeros_is_valid(self, client):
        r = await api_register(client, "bob", "0000")
        assert r.status_code == 303

    async def test_error_response_contains_error_message(self, client):
        r = await api_register(client, "bob", "12")
        assert b"PIN" in r.content or b"pin" in r.content or b"chiffre" in r.content.lower()


class TestLoginPage:
    async def test_get_returns_200(self, client):
        r = await client.get("/login")
        assert r.status_code == 200

    async def test_get_contains_form(self, client):
        r = await client.get("/login")
        assert b"<form" in r.content
        assert b'name="username"' in r.content
        assert b'name="pin"' in r.content

    async def test_has_link_to_register(self, client):
        r = await client.get("/login")
        assert b"/register" in r.content


class TestLoginPost:
    async def test_success_redirects_to_home(self, client, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        r = await client.post("/login", data={"username": "alice", "pin": "1234"})
        assert r.status_code == 303
        assert r.headers["location"] == "/"

    async def test_success_sets_session_cookie(self, client, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        r = await client.post("/login", data={"username": "alice", "pin": "1234"})
        assert "session" in r.headers.get("set-cookie", "").lower()

    async def test_wrong_pin_returns_401(self, client, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        r = await client.post("/login", data={"username": "alice", "pin": "9999"})
        assert r.status_code == 401

    async def test_unknown_user_returns_401(self, client):
        r = await client.post("/login", data={"username": "nobody", "pin": "1234"})
        assert r.status_code == 401

    async def test_empty_username_returns_401(self, client):
        r = await client.post("/login", data={"username": "", "pin": "1234"})
        assert r.status_code == 401

    async def test_empty_pin_returns_401(self, client, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        r = await client.post("/login", data={"username": "alice", "pin": ""})
        assert r.status_code == 401

    async def test_wrong_case_username_returns_401(self, client, db_pool):
        """Login is case-sensitive on username."""
        await db_create_user(db_pool, "alice", pin="1234")
        r = await client.post("/login", data={"username": "Alice", "pin": "1234"})
        assert r.status_code == 401

    async def test_after_login_home_is_accessible(self, client, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await api_login(client, "alice", "1234")
        r = await client.get("/")
        assert r.status_code == 200

    async def test_unauthenticated_home_redirects_to_login(self, client):
        r = await client.get("/")
        assert r.status_code == 302
        assert "login" in r.headers["location"]

    async def test_error_message_shown_on_bad_credentials(self, client, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        r = await client.post("/login", data={"username": "alice", "pin": "0000"})
        assert r.status_code == 401
        assert b"Invalid" in r.content or b"incorrect" in r.content or b"invalide" in r.content.lower()


class TestLogout:
    async def test_redirects_to_login(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        await api_login(client, "alice")
        r = await client.get("/logout")
        assert r.status_code == 303
        assert "login" in r.headers["location"]

    async def test_clears_session(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        await api_login(client, "alice")
        await client.get("/logout")
        r = await client.get("/")
        assert r.status_code == 302
        assert "login" in r.headers["location"]

    async def test_logout_without_session_still_redirects(self, client):
        r = await client.get("/logout")
        assert r.status_code == 303
        assert "login" in r.headers["location"]

    async def test_cannot_reuse_session_after_logout(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        await api_login(client, "alice")
        await client.get("/logout")
        # Protected endpoint should redirect after logout
        r = await client.get("/profile")
        assert r.status_code == 302

    async def test_double_logout_is_safe(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        await api_login(client, "alice")
        r1 = await client.get("/logout")
        r2 = await client.get("/logout")
        assert r1.status_code == 303
        assert r2.status_code == 303


class TestSessionLifecycle:
    async def test_all_protected_routes_redirect_when_unauthenticated(self, client):
        protected = ["/", "/profile", "/admin"]
        for path in protected:
            r = await client.get(path)
            assert r.status_code in (302, 303), f"{path} should redirect, got {r.status_code}"
            assert "login" in r.headers.get("location", "")

    async def test_post_routes_redirect_when_unauthenticated(self, client):
        endpoints = [
            ("/book", {"slot_id": 1, "type": "player"}),
            ("/cancel", {"booking_id": 1, "slot_id": 1}),
            ("/profile/pin", {"current_pin": "1234", "new_pin": "5678", "confirm_pin": "5678"}),
        ]
        for path, data in endpoints:
            r = await client.post(path, data=data)
            assert r.status_code in (302, 303), f"POST {path} should redirect, got {r.status_code}"
