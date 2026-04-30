"""
Diagnostic tests — delete this file once everything works.
"""
import json


class TestDiagnostic:
    async def test_app_is_reachable(self, client):
        r = await client.get("/login")
        assert r.status_code == 200

    async def test_show_raw_stored_value(self, db_pool):
        """Show exactly what is stored in the data column after insert."""
        data = json.dumps({"username": "rawcheck", "pin": "1234", "role": "player", "created_at": "2099-01-01"})
        await db_pool.execute("INSERT INTO users (data) VALUES ($1::jsonb)", data)

        # Select raw text to see what's actually stored
        raw = await db_pool.fetchval("SELECT data::text FROM users LIMIT 1")
        raise AssertionError(f"Stored value: {raw!r}")

    async def test_truncate_is_on_same_db_as_app(self, client, db_pool):
        """Register via app, verify visible in runner DB."""
        r = await client.post("/register", data={"username": "reguser", "pin": "4321"})
        assert r.status_code == 303
        raw = await db_pool.fetchval("SELECT data::text FROM users WHERE data->>'username' = 'reguser'")
        assert raw is not None, "DIFFERENT DATABASES"
        raise AssertionError(f"App-inserted value: {raw!r}")
