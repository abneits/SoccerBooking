"""
Shared helpers: direct DB seed functions + HTTP auth helpers + time control.

All DB helpers take an asyncpg pool/connection as first arg.
All API helpers take an httpx.AsyncClient.

Time helpers require TESTING=true on the app (POST /internal/set-time).
"""

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import asyncpg
import httpx

from tests.conftest import APP_URL

# ── Timezone constants ────────────────────────────────────────────────────────

TZ = ZoneInfo("Europe/Paris")

# A fixed Wednesday to use as the slot date in state-sensitive tests.
# Pick one far enough in the future that the DB date uniqueness index doesn't
# collide with real app usage, but any Wednesday works.
TEST_WEDNESDAY = "2099-04-02"  # Wednesday

# Canonical datetimes relative to TEST_WEDNESDAY:
#   Monday 2099-03-31, Wednesday 2099-04-02
OPEN_TIME   = datetime(2099, 3, 31, 14,  0, tzinfo=TZ)   # Monday 14:00   → OPEN
CLOSED_TIME = datetime(2099, 4,  2, 18, 30, tzinfo=TZ)   # Wednesday 18:30 → CLOSED
FROZEN_TIME = datetime(2099, 4,  2, 20,  0, tzinfo=TZ)   # Wednesday 20:00 → FROZEN
PRE_OPEN_TIME = datetime(2099, 3, 31, 11, 0, tzinfo=TZ)  # Monday 11:00   → FROZEN (before noon)


# ── Internal helpers ─────────────────────────────────────────────────────────

def _data(row) -> dict:
    """Return row['data'] as a dict regardless of whether asyncpg decoded it."""
    d = row["data"]
    return json.loads(d) if isinstance(d, str) else d


# ── DB seed helpers ───────────────────────────────────────────────────────────

async def db_create_user(
    pool: asyncpg.Pool,
    username: str,
    pin: str = "1234",
    role: str = "player",
) -> dict:
    data = {
        "username": username,
        "pin": pin,
        "role": role,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    row = await pool.fetchrow(
        "INSERT INTO users (data) VALUES ($1) RETURNING id, data", data
    )
    return {"id": row["id"], **_data(row)}


async def db_create_slot(
    pool: asyncpg.Pool,
    date: str,
    status: str = "open",
    cancelled_reason: Optional[str] = None,
) -> dict:
    data = {
        "date": date,
        "status": status,
        "cancelled_reason": cancelled_reason,
        "nudge_sent": False,
        "details": {},
    }
    row = await pool.fetchrow(
        "INSERT INTO slots (data) VALUES ($1) RETURNING id, data", data
    )
    return {"id": row["id"], **_data(row)}


async def db_create_booking(
    pool: asyncpg.Pool,
    slot_id: int,
    user_id: Optional[int],
    booked_by_id: int,
    booking_type: str = "player",
    guest_name: Optional[str] = None,
    status: str = "confirmed",
    position: Optional[int] = None,
) -> dict:
    if position is None:
        position = await pool.fetchval(
            "SELECT COALESCE(MAX((data->>'position')::int), 0) + 1 "
            "FROM bookings WHERE (data->>'slot_id')::int = $1",
            slot_id,
        )
    data = {
        "slot_id": slot_id,
        "user_id": user_id,
        "booked_by_id": booked_by_id,
        "type": booking_type,
        "guest_name": guest_name,
        "status": status,
        "position": position,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    row = await pool.fetchrow(
        "INSERT INTO bookings (data) VALUES ($1) RETURNING id, data", data
    )
    return {"id": row["id"], **_data(row)}


async def db_fill_slot(
    pool: asyncpg.Pool,
    slot_id: int,
    confirmed: int = 10,
    waitlist: int = 0,
) -> list[dict]:
    """Fill a slot with synthetic users up to confirmed + waitlist bookings."""
    bookings = []
    for i in range(confirmed + waitlist):
        u = await db_create_user(pool, f"filler_{slot_id}_{i}", pin="9999")
        status = "confirmed" if i < confirmed else "waitlist"
        b = await db_create_booking(pool, slot_id, u["id"], u["id"], status=status)
        bookings.append(b)
    return bookings


async def db_fetch_bookings(pool: asyncpg.Pool, slot_id: int) -> list[dict]:
    rows = await pool.fetch(
        "SELECT id, data FROM bookings WHERE (data->>'slot_id')::int = $1 "
        "ORDER BY (data->>'position')::int",
        slot_id,
    )
    return [{"id": r["id"], **_data(r)} for r in rows]


async def db_count_bookings(pool: asyncpg.Pool) -> int:
    return await pool.fetchval("SELECT COUNT(*) FROM bookings")


async def db_get_slot(pool: asyncpg.Pool, slot_id: int) -> Optional[dict]:
    row = await pool.fetchrow("SELECT id, data FROM slots WHERE id = $1", slot_id)
    if row is None:
        return None
    return {"id": row["id"], **_data(row)}


async def db_get_user(pool: asyncpg.Pool, user_id: int) -> Optional[dict]:
    row = await pool.fetchrow("SELECT id, data FROM users WHERE id = $1", user_id)
    if row is None:
        return None
    return {"id": row["id"], **_data(row)}


# ── HTTP helpers ──────────────────────────────────────────────────────────────

async def api_login(client: httpx.AsyncClient, username: str, pin: str = "1234") -> None:
    """POST /login and store the session cookie on the client."""
    resp = await client.post("/login", data={"username": username, "pin": pin})
    assert resp.status_code == 303, f"Login failed for {username!r}: {resp.status_code}"


async def api_register(
    client: httpx.AsyncClient, username: str, pin: str = "1234"
) -> httpx.Response:
    return await client.post("/register", data={"username": username, "pin": pin})


# ── Time control helpers ──────────────────────────────────────────────────────

async def set_time(client: httpx.AsyncClient, dt: datetime) -> None:
    """Override the app clock. Requires TESTING=true on the app."""
    r = await client.post("/internal/set-time", json={"iso": dt.isoformat()})
    assert r.status_code == 200, f"set_time failed: {r.status_code} {r.text}"


async def reset_time(client: httpx.AsyncClient) -> None:
    """Restore the real system clock."""
    r = await client.post("/internal/reset-time")
    assert r.status_code == 200, f"reset_time failed: {r.status_code} {r.text}"


async def get_effective_time(client: httpx.AsyncClient) -> dict:
    """Return the current effective time as seen by the app."""
    r = await client.get("/internal/now")
    assert r.status_code == 200
    return r.json()


@asynccontextmanager
async def at_time(client: httpx.AsyncClient, dt: datetime):
    """Context manager: set app time to dt, reset to real time on exit.

    Usage:
        async with at_time(client, OPEN_TIME):
            resp = await client.post("/book", ...)
    """
    await set_time(client, dt)
    try:
        yield
    finally:
        await reset_time(client)


# ── Legacy date constants (kept for backward compat with existing tests) ──────

WEDNESDAY_PAST   = "2020-03-25"   # always FROZEN (past date)
WEDNESDAY_FUTURE = "2099-04-02"   # TEST_WEDNESDAY alias


async def ui_login(page, username: str, pin: str = "1234") -> None:
    """Navigate to /login and submit credentials."""
    await page.goto("/login")
    await page.fill('input[name="username"]', username)
    await page.fill('input[name="pin"]', pin)
    await page.click('button[type="submit"]')
    await page.wait_for_url("**/", timeout=5000)


async def ui_set_time(page, dt: datetime) -> None:
    """Override app clock from Playwright (uses fetch via page.evaluate)."""
    iso = dt.isoformat()
    result = await page.evaluate(f"""
        fetch('/internal/set-time', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{iso: '{iso}'}})
        }}).then(r => r.json())
    """)
    return result


async def ui_reset_time(page) -> None:
    """Reset app clock from Playwright."""
    await page.evaluate("""
        fetch('/internal/reset-time', {method: 'POST'})
    """)
