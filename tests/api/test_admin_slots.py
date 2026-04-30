"""
API tests — Admin: slot management
Covers GET /admin, POST /admin/slot/cancel (by id and by date).
"""

import pytest
from tests.helpers import (
    db_create_user,
    db_create_slot,
    db_create_booking,
    db_get_slot,
    api_login,
)


class TestAdminAccess:
    async def test_unauthenticated_redirects_to_login(self, client):
        r = await client.get("/admin")
        assert r.status_code == 302
        assert "login" in r.headers["location"]

    async def test_player_redirected_to_home(self, client, db_pool):
        await db_create_user(db_pool, "alice", role="player")
        await api_login(client, "alice")
        r = await client.get("/admin")
        assert r.status_code == 302
        assert r.headers["location"] == "/"

    async def test_admin_can_access_panel(self, admin_client):
        r = await admin_client.get("/admin")
        assert r.status_code == 200

    async def test_admin_panel_shows_user_list(self, admin_client, db_pool):
        await db_create_user(db_pool, "visible_user")
        r = await admin_client.get("/admin")
        assert b"visible_user" in r.content

    async def test_admin_panel_shows_slot_list(self, admin_client, db_pool):
        await db_create_slot(db_pool, "2020-03-25")
        r = await admin_client.get("/admin")
        assert b"2020-03-25" in r.content

    async def test_admin_panel_shows_current_slot(self, admin_client, db_pool):
        """current_slot should be the slot with date >= today (upcoming), not oldest."""
        await db_create_slot(db_pool, "2020-03-25")   # past
        await db_create_slot(db_pool, "2099-03-25")   # future → should be current
        r = await admin_client.get("/admin")
        assert b"2099-03-25" in r.content

    async def test_admin_panel_falls_back_to_most_recent_when_all_past(self, admin_client, db_pool):
        await db_create_slot(db_pool, "2020-03-18")
        await db_create_slot(db_pool, "2020-03-25")  # most recent past
        r = await admin_client.get("/admin")
        assert b"2020-03-25" in r.content

    async def test_non_admin_cannot_post_to_admin_routes(self, client, db_pool):
        await db_create_user(db_pool, "alice", role="player")
        slot = await db_create_slot(db_pool, "2020-03-25")
        await api_login(client, "alice")
        r = await client.post("/admin/slot/cancel", data={"slot_id": slot["id"]})
        assert r.status_code == 302


class TestCancelSlotById:
    async def test_cancel_existing_slot(self, admin_client, db_pool):
        slot = await db_create_slot(db_pool, "2020-03-25")
        r = await admin_client.post("/admin/slot/cancel", data={"slot_id": slot["id"]})
        assert r.status_code == 303
        updated = await db_get_slot(db_pool, slot["id"])
        assert updated["status"] == "cancelled"

    async def test_cancel_stores_reason(self, admin_client, db_pool):
        slot = await db_create_slot(db_pool, "2020-03-25")
        await admin_client.post(
            "/admin/slot/cancel", data={"slot_id": slot["id"], "reason": "Intempéries"}
        )
        updated = await db_get_slot(db_pool, slot["id"])
        assert updated["cancelled_reason"] == "Intempéries"

    async def test_cancel_without_reason_stores_empty_string(self, admin_client, db_pool):
        slot = await db_create_slot(db_pool, "2020-03-25")
        await admin_client.post("/admin/slot/cancel", data={"slot_id": slot["id"]})
        updated = await db_get_slot(db_pool, slot["id"])
        assert updated["status"] == "cancelled"

    async def test_cancel_nonexistent_slot_returns_404(self, admin_client):
        r = await admin_client.post("/admin/slot/cancel", data={"slot_id": 999999})
        assert r.status_code == 404

    async def test_cancel_already_cancelled_slot_is_idempotent(self, admin_client, db_pool):
        slot = await db_create_slot(db_pool, "2020-03-25", status="cancelled")
        r = await admin_client.post(
            "/admin/slot/cancel", data={"slot_id": slot["id"], "reason": "Again"}
        )
        assert r.status_code == 303
        updated = await db_get_slot(db_pool, slot["id"])
        assert updated["status"] == "cancelled"
        assert updated["cancelled_reason"] == "Again"

    async def test_cancel_redirects_to_admin(self, admin_client, db_pool):
        slot = await db_create_slot(db_pool, "2020-03-25")
        r = await admin_client.post("/admin/slot/cancel", data={"slot_id": slot["id"]})
        assert r.status_code == 303
        assert r.headers["location"] == "/admin"


class TestPreCancelSlotByDate:
    async def test_creates_cancelled_slot_if_none_exists(self, admin_client, db_pool):
        r = await admin_client.post(
            "/admin/slot/cancel", data={"date": "2099-06-04", "reason": "Férié"}
        )
        assert r.status_code == 303
        row = await db_pool.fetchrow(
            "SELECT data FROM slots WHERE data->>'date' = '2099-06-04'"
        )
        assert row is not None
        assert row["data"]["status"] == "cancelled"
        assert row["data"]["cancelled_reason"] == "Férié"

    async def test_updates_existing_slot_by_date(self, admin_client, db_pool):
        slot = await db_create_slot(db_pool, "2020-03-25")
        await admin_client.post(
            "/admin/slot/cancel", data={"date": "2020-03-25", "reason": "Updated"}
        )
        updated = await db_get_slot(db_pool, slot["id"])
        assert updated["status"] == "cancelled"
        assert updated["cancelled_reason"] == "Updated"

    async def test_does_not_create_duplicate_slot_for_same_date(self, admin_client, db_pool):
        await db_create_slot(db_pool, "2020-03-25")
        await admin_client.post("/admin/slot/cancel", data={"date": "2020-03-25"})
        count = await db_pool.fetchval(
            "SELECT COUNT(*) FROM slots WHERE data->>'date' = '2020-03-25'"
        )
        assert count == 1

    async def test_precancel_with_reason_stored(self, admin_client, db_pool):
        r = await admin_client.post(
            "/admin/slot/cancel", data={"date": "2099-09-10", "reason": "Vacances"}
        )
        assert r.status_code == 303
        row = await db_pool.fetchrow(
            "SELECT data FROM slots WHERE data->>'date' = '2099-09-10'"
        )
        assert row["data"]["cancelled_reason"] == "Vacances"

    async def test_submitting_neither_id_nor_date_is_no_op(self, admin_client):
        """Neither slot_id nor date → no-op, redirect."""
        r = await admin_client.post("/admin/slot/cancel", data={})
        assert r.status_code == 303
