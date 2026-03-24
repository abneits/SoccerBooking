import asyncio
import json
import os
from datetime import datetime

import pytest
import asyncpg
from httpx import AsyncClient, ASGITransport

# Set env vars before importing the app
os.environ.setdefault("DATABASE_URL", "postgresql://soccer:soccer@localhost:5432/soccerbooking_test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-production")
os.environ.setdefault("WEBHOOK_URL", "")
os.environ.setdefault("TIMEZONE", "Europe/Paris")
os.environ.setdefault("SESSION_MAX_AGE", "3600")

from backend.main import app
from backend import db as db_module


# ── Session fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_db():
    """Create schema once per test session; tear down pool afterwards."""
    dsn = os.environ["DATABASE_URL"]
    await db_module.init_pool(dsn)
    pool = db_module.get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS bookings, slots, users CASCADE")
        await conn.execute("""
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                data JSONB NOT NULL
            )
        """)
        await conn.execute(
            "CREATE UNIQUE INDEX users_username_idx ON users ((data->>'username'))"
        )
        await conn.execute("""
            CREATE TABLE slots (
                id SERIAL PRIMARY KEY,
                data JSONB NOT NULL
            )
        """)
        await conn.execute(
            "CREATE UNIQUE INDEX slots_date_idx ON slots ((data->>'date'))"
        )
        await conn.execute("""
            CREATE TABLE bookings (
                id SERIAL PRIMARY KEY,
                data JSONB NOT NULL
            )
        """)
    yield
    await db_module.close_pool()


# ── Per-test fixture ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
async def clean_db():
    """Truncate all tables before each test for isolation."""
    pool = db_module.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "TRUNCATE bookings, slots, users RESTART IDENTITY CASCADE"
        )
    yield


# ── HTTP client ───────────────────────────────────────────────────────────────

@pytest.fixture
async def client():
    """Async HTTP client backed by the FastAPI test transport."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


# ── DB helpers ────────────────────────────────────────────────────────────────

async def create_user(username: str, pin: str = "1234", role: str = "player") -> dict:
    """Insert a user row and return {id, username, pin, role, created_at}."""
    data = json.dumps({
        "username": username,
        "pin": pin,
        "role": role,
        "created_at": datetime.utcnow().isoformat(),
    })
    row = await db_module.fetch_one(
        "INSERT INTO users (data) VALUES ($1::jsonb) RETURNING id, data", data
    )
    return {"id": row["id"], **row["data"]}


async def create_slot(date: str, status: str = "open") -> dict:
    """Insert a slot row and return {id, date, status, ...}."""
    data = json.dumps({
        "date": date,
        "status": status,
        "cancelled_reason": None,
        "nudge_sent": False,
        "details": {},
    })
    row = await db_module.fetch_one(
        "INSERT INTO slots (data) VALUES ($1::jsonb) RETURNING id, data", data
    )
    return {"id": row["id"], **row["data"]}


async def login(client: AsyncClient, username: str, pin: str = "1234") -> None:
    """POST /login and follow redirect; client retains the session cookie."""
    await client.post("/login", data={"username": username, "pin": pin})
