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

    async def test_insert_with_explicit_transaction(self, db_pool):
        """Insert inside explicit transaction with commit."""
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                data = json.dumps({"username": "txuser", "pin": "1234", "role": "player", "created_at": "2099-01-01"})
                await conn.execute("INSERT INTO users (data) VALUES ($1::jsonb)", data)
            # After transaction block commits, check visibility
            row = await conn.fetchrow("SELECT id FROM users WHERE data->>'username' = 'txuser'")
            assert row is not None, "Not found after explicit transaction commit"

    async def test_insert_without_transaction(self, db_pool):
        """Insert without explicit transaction — asyncpg autocommit behavior."""
        async with db_pool.acquire() as conn:
            data = json.dumps({"username": "notxuser", "pin": "1234", "role": "player", "created_at": "2099-01-01"})
            # Execute without transaction block
            await conn.execute("INSERT INTO users (data) VALUES ($1::jsonb)", data)
            row = await conn.fetchrow("SELECT id FROM users WHERE data->>'username' = 'notxuser'")
            assert row is not None, "Not found — asyncpg may not autocommit without transaction block"

    async def test_truncate_is_on_same_db_as_app(self, client, db_pool):
        """Register via app, verify visible in runner DB."""
        r = await client.post("/register", data={"username": "reguser", "pin": "4321"})
        assert r.status_code == 303, f"Register failed: {r.status_code}"
        row = await db_pool.fetchrow("SELECT id FROM users WHERE data->>'username' = 'reguser'")
        assert row is not None, "User registered via app but not found in runner DB — DIFFERENT DATABASES"
