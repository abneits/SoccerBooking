"""Diagnostic — what does GET / actually return inside at_time(OPEN_TIME)?"""

from tests.helpers import (
    db_create_user,
    db_create_slot,
    api_login,
    at_time,
    TEST_WEDNESDAY,
    OPEN_TIME,
)


class TestDiag:
    async def test_show_response(self, client, db_pool):
        await db_create_user(db_pool, "alice")
        await db_create_slot(db_pool, TEST_WEDNESDAY)
        await api_login(client, "alice")

        # Verify time is overridden during the GET
        async with at_time(client, OPEN_TIME):
            now_before = await client.get("/internal/now")
            r = await client.get("/")
            now_during = await client.get("/internal/now")

        # Show all relevant info
        raise AssertionError(
            f"\n\nat_time set to: {OPEN_TIME.isoformat()}"
            f"\nbefore GET /: {now_before.json()}"
            f"\nduring GET /: {now_during.json()}"
            f"\nstatus: {r.status_code}"
            f"\nresponse text:\n{'-'*60}\n{r.text}\n{'-'*60}"
        )
