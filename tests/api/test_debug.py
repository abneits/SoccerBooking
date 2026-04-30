"""
Diagnostic tests — delete this file once everything works.
"""
import json


class TestDiagnostic:
    async def test_app_is_reachable(self, client):
        r = await client.get("/login")
        assert r.status_code == 200

    async def test_db_count_after_truncate(self, db_pool):
        count = await db_pool.fetchval("SELECT COUNT(*) FROM users")
        assert count == 0

    async def test_insert_same_connection(self, db_pool):
        """Insert and select on the same connection — rules out transaction isolation."""
        async with db_pool.acquire() as conn:
            data = json.dumps({"username": "sameconn", "pin": "1234", "role": "player", "created_at": "2099-01-01"})
            await conn.execute("INSERT INTO users (data) VALUES ($1::jsonb)", data)
            row = await conn.fetchrow("SELECT id FROM users WHERE data->>'username' = 'sameconn'")
            assert row is not None, "Insert not visible on same connection — autocommit issue"

    async def test_insert_different_connections(self, db_pool):
        """Insert on one connection, select on another — tests transaction commit."""
        data = json.dumps({"username": "diffconn", "pin": "1234", "role": "player", "created_at": "2099-01-01"})
        await db_pool.execute("INSERT INTO users (data) VALUES ($1::jsonb)", data)
        # Different connection from pool
        row = await db_pool.fetchrow("SELECT id FROM users WHERE data->>'username' = 'diffconn'")
        assert row is not None, "Insert not visible on different connection — not committed"

    async def test_login_after_same_conn_insert(self, client, db_pool):
        """Insert on same connection, then login via app."""
        async with db_pool.acquire() as conn:
            data = json.dumps({"username": "logintest", "pin": "1234", "role": "player", "created_at": "2099-01-01"})
            await conn.execute("INSERT INTO users (data) VALUES ($1::jsonb)", data)
        r = await client.post("/login", data={"username": "logintest", "pin": "1234"})
        assert r.status_code == 303, f"Login failed: {r.status_code}"
