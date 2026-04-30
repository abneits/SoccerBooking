"""
Diagnostic tests — run these first to verify DB/app connectivity.
Delete this file once everything works.
"""
import json


class TestDiagnostic:
    async def test_app_is_reachable(self, client):
        r = await client.get("/login")
        assert r.status_code == 200, f"App not reachable: {r.status_code}"

    async def test_db_count_after_truncate(self, db_pool):
        count = await db_pool.fetchval("SELECT COUNT(*) FROM users")
        assert count == 0, f"Expected 0 users after truncate, got {count}"

    async def test_raw_insert_and_select(self, db_pool):
        """Insert raw JSON string (no codec), verify select works."""
        data = json.dumps({"username": "rawuser", "pin": "1234", "role": "player", "created_at": "2099-01-01"})
        await db_pool.execute("INSERT INTO users (data) VALUES ($1::jsonb)", data)
        row = await db_pool.fetchrow(
            "SELECT id, data FROM users WHERE data->>'username' = 'rawuser'"
        )
        assert row is not None, "Raw insert not found"
        # Show what data looks like
        assert True, f"data type: {type(row['data'])}, value: {row['data']!r}"

    async def test_codec_insert_and_select(self, db_pool):
        """Insert via helper (uses codec), verify select works."""
        from tests.helpers import db_create_user
        await db_create_user(db_pool, "codecuser", pin="1234")
        row = await db_pool.fetchrow(
            "SELECT id, data FROM users WHERE data->>'username' = 'codecuser'"
        )
        assert row is not None, f"Codec insert not found. Check if _init_conn double-encodes JSON."

    async def test_login_after_raw_insert(self, client, db_pool):
        """Raw insert then login via app."""
        data = json.dumps({"username": "logintest", "pin": "1234", "role": "player", "created_at": "2099-01-01"})
        await db_pool.execute("INSERT INTO users (data) VALUES ($1::jsonb)", data)
        r = await client.post("/login", data={"username": "logintest", "pin": "1234"})
        assert r.status_code == 303, f"Login failed: {r.status_code} — DB/app mismatch or insert failed"
