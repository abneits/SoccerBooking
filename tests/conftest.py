"""
Black-box test suite for SoccerBooking.

Requires two environment variables:
  APP_URL      – base URL of the running app  (e.g. http://localhost:8008)
  DATABASE_URL – direct Postgres DSN for setup/teardown

The DB is truncated before every test for full isolation.
The app itself is never imported — all interactions go through HTTP or raw SQL.
"""

import os

import asyncpg
import httpx
import pytest
from playwright.async_api import async_playwright

# ── Configuration ─────────────────────────────────────────────────────────────

APP_URL = os.environ.get("APP_URL", "http://localhost:8008").rstrip("/")
DATABASE_URL = os.environ["DATABASE_URL"]


# ── Database pool ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
async def db_pool():
    pool = await asyncpg.create_pool(DATABASE_URL)
    yield pool
    await pool.close()


@pytest.fixture(autouse=True)
async def reset_db(db_pool):
    """Truncate all tables before every test — full isolation."""
    async with db_pool.acquire() as conn:
        await conn.execute(
            "TRUNCATE bookings, slots, users RESTART IDENTITY CASCADE"
        )
    yield


# ── HTTP client (stateless — no shared cookies) ───────────────────────────────

@pytest.fixture
async def client():
    """Fresh httpx client per test. Does NOT follow redirects by default."""
    async with httpx.AsyncClient(base_url=APP_URL, follow_redirects=False) as c:
        yield c


@pytest.fixture
async def admin_client(db_pool):
    """Authenticated admin client, ready to use."""
    from tests.helpers import db_create_user, api_login
    async with httpx.AsyncClient(base_url=APP_URL, follow_redirects=False) as c:
        await db_create_user(db_pool, "testadmin", pin="0000", role="admin")
        await api_login(c, "testadmin", "0000")
        yield c


@pytest.fixture
async def player_client(db_pool):
    """Authenticated player client, ready to use."""
    from tests.helpers import db_create_user, api_login
    async with httpx.AsyncClient(base_url=APP_URL, follow_redirects=False) as c:
        await db_create_user(db_pool, "testplayer", pin="1111", role="player")
        await api_login(c, "testplayer", "1111")
        yield c


# ── Playwright browser (session-scoped, headless) ────────────────────────────

@pytest.fixture(scope="session")
async def browser():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        yield b
        await b.close()


@pytest.fixture
async def page(browser):
    """Fresh browser page per test."""
    ctx = await browser.new_context(base_url=APP_URL)
    p = await ctx.new_page()
    # Global navigation timeout: 10s max per goto/wait_for_url
    p.set_default_navigation_timeout(10000)
    p.set_default_timeout(10000)
    yield p
    await p.close()
    await ctx.close()
