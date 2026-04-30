"""
Diagnostic tests — delete this file once everything works.
Tests the EXACT data flow: write format, stored format, read format.
"""
import json


class TestDiagnostic:
    async def test_1_show_what_runner_inserts(self, db_pool):
        """Insert like helpers.py does, show what's stored."""
        data = json.dumps({"username": "runner_user", "pin": "1234", "role": "player"})
        await db_pool.execute("INSERT INTO users (data) VALUES ($1::jsonb)", data)
        # Read as raw text to see exactly what PostgreSQL stored
        raw = await db_pool.fetchval("SELECT data::text FROM users LIMIT 1")
        # Read with ->> operator
        username = await db_pool.fetchval("SELECT data->>'username' FROM users LIMIT 1")
        # Read the data column directly
        data_col = await db_pool.fetchval("SELECT data FROM users LIMIT 1")
        raise AssertionError(
            f"\n  raw::text = {raw!r}"
            f"\n  data->>'username' = {username!r}"
            f"\n  data column type = {type(data_col).__name__}, value = {data_col!r}"
        )

    async def test_2_show_what_app_inserts(self, client, db_pool):
        """Register via app HTTP, show what's stored."""
        r = await client.post("/register", data={"username": "app_user", "pin": "4321"})
        assert r.status_code == 303, f"Register failed: {r.status_code}"
        raw = await db_pool.fetchval("SELECT data::text FROM users WHERE data::text LIKE '%app_user%' LIMIT 1")
        username = await db_pool.fetchval("SELECT data->>'username' FROM users WHERE data::text LIKE '%app_user%' LIMIT 1")
        data_col = await db_pool.fetchval("SELECT data FROM users WHERE data::text LIKE '%app_user%' LIMIT 1")
        raise AssertionError(
            f"\n  raw::text = {raw!r}"
            f"\n  data->>'username' = {username!r}"
            f"\n  data column type = {type(data_col).__name__}, value = {data_col!r}"
        )

    async def test_3_login_app_user_then_runner_user(self, client, db_pool):
        """Create both, try to login both."""
        # App-created user
        await client.post("/register", data={"username": "appguy", "pin": "1111"})
        r1 = await client.post("/login", data={"username": "appguy", "pin": "1111"})

        # Runner-created user
        data = json.dumps({"username": "runnerguy", "pin": "2222", "role": "player", "created_at": "2099-01-01"})
        await db_pool.execute("INSERT INTO users (data) VALUES ($1::jsonb)", data)
        r2 = await client.post("/login", data={"username": "runnerguy", "pin": "2222"})

        raise AssertionError(
            f"\n  appguy login = {r1.status_code}"
            f"\n  runnerguy login = {r2.status_code}"
        )
