"""
Black-box test suite for SoccerBooking.

Requires two environment variables:
  APP_URL      – base URL of the running app  (e.g. http://192.168.x.x:8009)
  DATABASE_URL – direct Postgres DSN for setup/teardown

The DB is truncated before every test for full isolation.
The app itself is never imported — all interactions go through HTTP or raw SQL.

JSONB: no custom codec. Data is inserted as json.dumps() strings with ::jsonb
cast and decoded via helpers._data() on read. This matches how the app itself
works and avoids any codec/encoding mismatch.
"""

import os

import asyncpg
import httpx
import pytest
from playwright.async_api import async_playwright

# ── Configuration ─────────────────────────────────────────────────────────────

APP_URL = os.environ.get("APP_URL", "http://localhost:8009").rstrip("/")
DATABASE_URL = os.environ["DATABASE_URL"]


# ── Database pool ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
async def db_pool():
    """Fresh asyncpg pool per test. Truncates before yielding.
    No JSONB codec — matches how the app reads/writes JSONB.
    """
    pool = await asyncpg.create_pool(DATABASE_URL)
    async with pool.acquire() as conn:
        await conn.execute(
            "TRUNCATE bookings, slots, users RESTART IDENTITY CASCADE"
        )
    yield pool
    await pool.close()


# ── HTTP client ───────────────────────────────────────────────────────────────

@pytest.fixture
async def client():
    async with httpx.AsyncClient(base_url=APP_URL, follow_redirects=False) as c:
        yield c


@pytest.fixture
async def admin_client(db_pool):
    from tests.helpers import db_create_user, api_login
    async with httpx.AsyncClient(base_url=APP_URL, follow_redirects=False) as c:
        await db_create_user(db_pool, "testadmin", pin="0000", role="admin")
        await api_login(c, "testadmin", "0000")
        yield c


@pytest.fixture
async def player_client(db_pool):
    from tests.helpers import db_create_user, api_login
    async with httpx.AsyncClient(base_url=APP_URL, follow_redirects=False) as c:
        await db_create_user(db_pool, "testplayer", pin="1111", role="player")
        await api_login(c, "testplayer", "1111")
        yield c


# ── Playwright (function-scoped to share event loop with other fixtures) ────

@pytest.fixture
async def page():
    """Fresh browser + page per test.
    Function-scoped to share the event loop with db_pool — session-scoped
    Playwright fixtures conflict with per-test fixtures under pytest-asyncio.
    """
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(base_url=APP_URL)
        p = await ctx.new_page()
        p.set_default_navigation_timeout(10000)
        p.set_default_timeout(10000)
        yield p
        await ctx.close()
        await browser.close()
