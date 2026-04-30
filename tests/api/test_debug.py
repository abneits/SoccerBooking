"""
Diagnostic tests — run these first to verify DB/app connectivity.
Delete this file once everything works.
"""


class TestDiagnostic:
    async def test_db_insert_then_login(self, client, db_pool):
        """Create user directly in DB, then login via app — verifies same DB."""
        from tests.helpers import db_create_user
        import asyncpg

        # Insert directly
        await db_create_user(db_pool, "diaguser", pin="1234", role="player")

        # Verify it exists in DB
        row = await db_pool.fetchrow(
            "SELECT id, data FROM users WHERE data->>'username' = 'diaguser'"
        )
        assert row is not None, "User not found in DB after insert"

        # Login via app HTTP
        r = await client.post("/login", data={"username": "diaguser", "pin": "1234"})
        assert r.status_code == 303, (
            f"Login returned {r.status_code} — app and runner may be using different databases. "
            f"Check DATABASE_URL in .env.test (app) vs .env.runner (runner)."
        )

    async def test_db_count_after_truncate(self, db_pool):
        """Verify truncate works and DB is reachable."""
        count = await db_pool.fetchval("SELECT COUNT(*) FROM users")
        assert count == 0, f"Expected 0 users after truncate, got {count}"

    async def test_app_is_reachable(self, client):
        """Verify APP_URL is reachable."""
        r = await client.get("/login")
        assert r.status_code == 200, f"App not reachable: {r.status_code}"
