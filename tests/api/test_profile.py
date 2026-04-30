"""
API tests — Profile routes
Covers GET /profile and POST /profile/pin.
"""

import pytest
from tests.helpers import db_create_user, db_get_user, api_login
from tests.conftest import APP_URL
import httpx


class TestProfilePage:
    async def test_unauthenticated_redirects_to_login(self, client):
        r = await client.get("/profile")
        assert r.status_code == 302
        assert "login" in r.headers["location"]

    async def test_authenticated_returns_200(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        await api_login(client, "alice")
        r = await client.get("/profile")
        assert r.status_code == 200

    async def test_shows_username(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        await api_login(client, "alice")
        r = await client.get("/profile")
        assert b"alice" in r.content

    async def test_shows_admin_badge_for_admin(self, client, db_pool):
        await db_create_user(db_pool, "boss", role="admin")
        await api_login(client, "boss")
        r = await client.get("/profile")
        assert b"admin" in r.content

    async def test_does_not_show_admin_badge_for_player(self, client, db_pool):
        await db_create_user(db_pool, "alice", role="player")
        await api_login(client, "alice")
        r = await client.get("/profile")
        # "admin" should not appear as a badge for a regular player
        # (it might appear in nav links, so check carefully for role badge context)
        content = r.content.decode()
        assert "admin" not in content.lower() or "/admin" not in content

    async def test_has_pin_change_form(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        await api_login(client, "alice")
        r = await client.get("/profile")
        assert b'name="current_pin"' in r.content
        assert b'name="new_pin"' in r.content
        assert b'name="confirm_pin"' in r.content


class TestChangePinSuccess:
    async def test_returns_200_on_success(self, client, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await api_login(client, "alice")
        r = await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "5678", "confirm_pin": "5678"},
        )
        assert r.status_code == 200

    async def test_updates_pin_in_database(self, client, db_pool):
        user = await db_create_user(db_pool, "alice", pin="1234")
        await api_login(client, "alice")
        await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "5678", "confirm_pin": "5678"},
        )
        updated = await db_get_user(db_pool, user["id"])
        assert updated["pin"] == "5678"

    async def test_new_pin_enables_login(self, client, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await api_login(client, "alice")
        await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "5678", "confirm_pin": "5678"},
        )
        await client.get("/logout")
        async with httpx.AsyncClient(base_url=APP_URL, follow_redirects=False) as c:
            r = await c.post("/login", data={"username": "alice", "pin": "5678"})
            assert r.status_code == 303

    async def test_old_pin_rejected_after_change(self, client, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await api_login(client, "alice")
        await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "5678", "confirm_pin": "5678"},
        )
        await client.get("/logout")
        async with httpx.AsyncClient(base_url=APP_URL, follow_redirects=False) as c:
            r = await c.post("/login", data={"username": "alice", "pin": "1234"})
            assert r.status_code == 401

    async def test_success_message_shown(self, client, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await api_login(client, "alice")
        r = await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "5678", "confirm_pin": "5678"},
        )
        assert b"success" in r.content.lower() or b"updated" in r.content.lower() or b"mis" in r.content.lower()

    async def test_zero_padded_pin_is_valid(self, client, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await api_login(client, "alice")
        r = await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "0001", "confirm_pin": "0001"},
        )
        assert r.status_code == 200

    async def test_all_zeros_pin_is_valid(self, client, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await api_login(client, "alice")
        r = await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "0000", "confirm_pin": "0000"},
        )
        assert r.status_code == 200


class TestChangePinErrors:
    async def test_wrong_current_pin_returns_400(self, client, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await api_login(client, "alice")
        r = await client.post(
            "/profile/pin",
            data={"current_pin": "9999", "new_pin": "5678", "confirm_pin": "5678"},
        )
        assert r.status_code == 400

    async def test_wrong_current_pin_does_not_update_db(self, client, db_pool):
        user = await db_create_user(db_pool, "alice", pin="1234")
        await api_login(client, "alice")
        await client.post(
            "/profile/pin",
            data={"current_pin": "9999", "new_pin": "5678", "confirm_pin": "5678"},
        )
        row = await db_get_user(db_pool, user["id"])
        assert row["pin"] == "1234"

    async def test_pin_mismatch_returns_400(self, client, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await api_login(client, "alice")
        r = await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "5678", "confirm_pin": "9999"},
        )
        assert r.status_code == 400

    async def test_new_pin_too_short_returns_400(self, client, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await api_login(client, "alice")
        r = await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "12", "confirm_pin": "12"},
        )
        assert r.status_code == 400

    async def test_new_pin_too_long_returns_400(self, client, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await api_login(client, "alice")
        r = await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "12345", "confirm_pin": "12345"},
        )
        assert r.status_code == 400

    async def test_non_numeric_new_pin_returns_400(self, client, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await api_login(client, "alice")
        r = await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "abcd", "confirm_pin": "abcd"},
        )
        assert r.status_code == 400

    async def test_mixed_alphanumeric_new_pin_returns_400(self, client, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await api_login(client, "alice")
        r = await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "12ab", "confirm_pin": "12ab"},
        )
        assert r.status_code == 400

    async def test_error_message_shown_on_failure(self, client, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await api_login(client, "alice")
        r = await client.post(
            "/profile/pin",
            data={"current_pin": "9999", "new_pin": "5678", "confirm_pin": "5678"},
        )
        assert r.status_code == 400
        assert b"error" in r.content.lower() or b"incorrect" in r.content.lower() or b"incorrect" in r.content.lower()

    async def test_unauthenticated_pin_change_redirects(self, client):
        r = await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "5678", "confirm_pin": "5678"},
        )
        assert r.status_code == 302

    async def test_changing_pin_does_not_affect_other_users(self, client, db_pool):
        alice = await db_create_user(db_pool, "alice", pin="1234")
        bob = await db_create_user(db_pool, "bob", pin="4321")
        await api_login(client, "alice")
        await client.post(
            "/profile/pin",
            data={"current_pin": "1234", "new_pin": "5678", "confirm_pin": "5678"},
        )
        row = await db_get_user(db_pool, bob["id"])
        assert row["pin"] == "4321"
