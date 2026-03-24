# SoccerBooking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a mobile-first weekly soccer slot booking web app with FastAPI, Jinja2, HTMX, and PostgreSQL, self-hosted via Docker Compose.

**Architecture:** Server-rendered pages via Jinja2 + HTMX partial swaps. All state lives in PostgreSQL using a 3-table JSONB schema. Slot lifecycle states (OPEN/CLOSED/FROZEN) are computed at request time from the slot date and current timestamp — never stored. Business logic lives in pure utility functions, tested independently from the HTTP layer.

**Tech Stack:** Python 3.12, FastAPI, Starlette SessionMiddleware, Jinja2, HTMX, PostgreSQL 16, asyncpg, Alembic, APScheduler, Docker Compose, pytest, ruff

---

## Generation Constraints

These rules apply to every agent or worker executing this plan. They are non-negotiable.

**Environment**
- Do NOT attempt to run the project locally at any point during generation.
- The goal is solely to generate complete and functional source files.
- The database is remote and not accessible from this environment — do NOT attempt to connect to it or run migrations at any point.
- Do NOT run any git commands. Version control will be handled manually at a later stage.

**Docker**
- Once all source files are generated, produce a `Dockerfile` and `docker-compose.yml` ready to be built on a remote server.
- Do NOT run `docker build` or any command that requires a local Docker daemon.

**Database initialisation**
- Use **Alembic** for schema management. The first migration (`001_initial_schema.py`) contains the full data model: table creation, indexes, and constraints.
- Generate an `entrypoint.sh` script that runs `alembic upgrade head` automatically before starting the app — no manual migration step ever required.
- This approach is idempotent (safe to run on every container restart) and handles future schema changes naturally from a single source of truth.
- Do NOT generate a separate `init.sql`. Alembic is the canonical schema definition.

**Tests**
- Do NOT run or generate tests during the source-file generation phase.
- Once all source files and the `Dockerfile` are complete, generate all tests in `tests/`, clearly separated from the main source code.
- Tests will be executed later, after the Docker image has been deployed on the remote server.

**Assumptions & confirmations**
- Do NOT prompt for confirmation during generation. Make reasonable assumptions and document them in `ASSUMPTIONS.md` at the root of the project.
- Only pause and ask if a decision is a true blocker that cannot be reasonably inferred from the spec.

---

## File Structure

```
SoccerBooking/
├── docker-compose.yml
├── Dockerfile
├── entrypoint.sh            # Runs alembic upgrade head then starts uvicorn
├── ASSUMPTIONS.md           # Generated during implementation — documents all non-spec decisions
├── pyproject.toml
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py
├── backend/
│   ├── main.py              # FastAPI app factory, middleware, router registration, lifespan
│   ├── db.py                # asyncpg pool setup, query helpers (fetch_one, fetch_all, execute)
│   ├── config.py            # Settings from env vars (DATABASE_URL, SECRET_KEY, etc.)
│   ├── slot_utils.py        # compute_slot_state(), get_or_create_upcoming_slot(), next_wednesday()
│   ├── booking_utils.py     # create_booking(), cancel_booking(), promote_waitlist()
│   ├── webhooks.py          # fire_waitlist_promoted(), fire_slot_not_full() — async, fire-and-forget
│   ├── scheduler.py         # APScheduler setup, Wednesday 14:00 job
│   ├── auth.py              # get_current_user(), require_login(), require_admin() dependencies
│   ├── routers/
│   │   ├── auth.py          # /register, /login, /logout routes
│   │   ├── main.py          # / (GET), /book, /cancel (POST)
│   │   ├── admin.py         # /admin (GET), /admin/slot/*, /admin/booking/*, /admin/user/*
│   │   └── profile.py       # /profile (GET), /profile/pin (POST)
│   ├── templates/
│   │   ├── base.html        # HTML shell, nav, mobile viewport
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── profile.html
│   │   ├── index.html       # Main page with HTMX slot panel
│   │   ├── partials/
│   │   │   └── slot_panel.html  # HTMX-swappable: booking list + action buttons
│   │   └── admin/
│   │       ├── index.html
│   │       ├── partials/
│   │       │   ├── booking_list.html
│   │       │   └── user_list.html
│   └── static/
│       └── css/
│           └── main.css
└── tests/
    ├── conftest.py          # DB fixtures, test client, session helpers
    ├── test_slot_utils.py
    ├── test_booking_utils.py
    ├── test_auth_routes.py
    ├── test_main_routes.py
    ├── test_admin_routes.py
    └── test_profile_routes.py
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `backend/config.py`
- Create: `.env.example`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "soccerbooking"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.29",
    "jinja2>=3.1",
    "python-multipart>=0.0.9",
    "starlette>=0.37",
    "asyncpg>=0.29",
    "alembic>=1.13",
    "psycopg2-binary>=2.9",   # alembic sync driver
    "apscheduler>=3.10",
    "httpx>=0.27",
    "itsdangerous>=2.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
    "ruff>=0.4",
]

[tool.ruff]
line-length = 100

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 2: Create `entrypoint.sh`**

```bash
#!/bin/sh
set -e
alembic upgrade head
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 3: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install -e .
COPY . .
RUN chmod +x entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
```

- [ ] **Step 5: Create `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: soccerbooking
      POSTGRES_USER: soccer
      POSTGRES_PASSWORD: soccer
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  app:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      - db
    volumes:
      - .:/app

volumes:
  pgdata:
```

- [ ] **Step 6: Create `backend/config.py`**

```python
import os

DATABASE_URL = os.environ["DATABASE_URL"]
SECRET_KEY = os.environ["SECRET_KEY"]
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
TIMEZONE = os.environ.get("TIMEZONE", "Europe/Paris")
SESSION_MAX_AGE = int(os.environ.get("SESSION_MAX_AGE", "604800"))
```

- [ ] **Step 7: Create `.env.example`**

```
DATABASE_URL=postgresql://soccer:soccer@db:5432/soccerbooking
SECRET_KEY=change-me-in-production
WEBHOOK_URL=https://your-webhook-url
TIMEZONE=Europe/Paris
SESSION_MAX_AGE=604800
```

- [ ] **Step 6: Create empty `backend/__init__.py` and `backend/routers/__init__.py`**

```bash
mkdir -p backend/routers backend/templates/partials backend/templates/admin/partials backend/static/css tests
touch backend/__init__.py backend/routers/__init__.py
```

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml Dockerfile docker-compose.yml backend/config.py .env.example backend/__init__.py backend/routers/__init__.py
git commit -m "chore: project scaffolding"
```

---

## Task 2: Database Layer

**Files:**
- Create: `backend/db.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/001_initial_schema.py`

- [ ] **Step 1: Create `backend/db.py`**

```python
import asyncpg

_pool: asyncpg.Pool | None = None


async def init_pool(dsn: str) -> None:
    global _pool
    _pool = await asyncpg.create_pool(dsn)


async def close_pool() -> None:
    if _pool:
        await _pool.close()


def get_pool() -> asyncpg.Pool:
    assert _pool is not None, "DB pool not initialized"
    return _pool


async def fetch_one(query: str, *args) -> dict | None:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row else None


async def fetch_all(query: str, *args) -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(query, *args)
        return [dict(r) for r in rows]


async def execute(query: str, *args) -> str:
    async with get_pool().acquire() as conn:
        return await conn.execute(query, *args)


async def fetch_val(query: str, *args):
    async with get_pool().acquire() as conn:
        return await conn.fetchval(query, *args)
```

- [ ] **Step 2: Initialise Alembic**

```bash
pip install -e ".[dev]"
alembic init alembic
```

- [ ] **Step 3: Edit `alembic/env.py`** to point at `DATABASE_URL` from env:

In `alembic/env.py`, replace the `sqlalchemy.url` configuration block:

```python
import os
from logging.config import fileConfig
from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=None, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    from sqlalchemy import engine_from_config, pool
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Create migration `alembic/versions/001_initial_schema.py`**

```python
"""initial schema"""
revision = "001"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


def upgrade() -> None:
    op.execute("""
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            data JSONB NOT NULL
        )
    """)
    op.execute("CREATE UNIQUE INDEX users_username_idx ON users ((data->>'username'))")
    op.execute("CREATE INDEX users_data_gin ON users USING GIN (data)")

    op.execute("""
        CREATE TABLE slots (
            id SERIAL PRIMARY KEY,
            data JSONB NOT NULL
        )
    """)
    op.execute("CREATE UNIQUE INDEX slots_date_idx ON slots ((data->>'date'))")
    op.execute("CREATE INDEX slots_data_gin ON slots USING GIN (data)")

    op.execute("""
        CREATE TABLE bookings (
            id SERIAL PRIMARY KEY,
            data JSONB NOT NULL
        )
    """)
    op.execute("CREATE INDEX bookings_data_gin ON bookings USING GIN (data)")


def downgrade() -> None:
    op.execute("DROP TABLE bookings")
    op.execute("DROP TABLE slots")
    op.execute("DROP TABLE users")
```

- [ ] **Step 5: Run migration against local DB**

```bash
docker compose up -d db
DATABASE_URL=postgresql://soccer:soccer@localhost:5432/soccerbooking alembic upgrade head
```

Expected: `Running upgrade  -> 001, initial schema`

- [ ] **Step 6: Commit**

```bash
git add backend/db.py alembic.ini alembic/
git commit -m "feat: database layer and initial schema migration"
```

---

## Task 3: Test Infrastructure

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `tests/conftest.py`**

```python
import asyncio
import os
import pytest
import asyncpg
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("DATABASE_URL", "postgresql://soccer:soccer@localhost:5432/soccerbooking_test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("WEBHOOK_URL", "")
os.environ.setdefault("TIMEZONE", "Europe/Paris")

from backend.main import app
from backend import db as db_module


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_db():
    """Create test DB schema once per session."""
    dsn = os.environ["DATABASE_URL"]
    await db_module.init_pool(dsn)
    pool = db_module.get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS bookings, slots, users CASCADE")
        await conn.execute("CREATE TABLE users (id SERIAL PRIMARY KEY, data JSONB NOT NULL)")
        await conn.execute("CREATE UNIQUE INDEX users_username_idx ON users ((data->>'username'))")
        await conn.execute("CREATE TABLE slots (id SERIAL PRIMARY KEY, data JSONB NOT NULL)")
        await conn.execute("CREATE UNIQUE INDEX slots_date_idx ON slots ((data->>'date'))")
        await conn.execute("CREATE TABLE bookings (id SERIAL PRIMARY KEY, data JSONB NOT NULL)")
    yield
    await db_module.close_pool()


@pytest.fixture(autouse=True)
async def clean_db():
    """Truncate tables before each test."""
    pool = db_module.get_pool()
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE bookings, slots, users RESTART IDENTITY CASCADE")
    yield


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def create_user(username: str, pin: str = "1234", role: str = "player") -> dict:
    from datetime import datetime
    row = await db_module.fetch_one(
        "INSERT INTO users (data) VALUES ($1::jsonb) RETURNING id, data",
        f'{{"username": "{username}", "pin": "{pin}", "role": "{role}", "created_at": "{datetime.utcnow().isoformat()}"}}'
    )
    return {"id": row["id"], **row["data"]}


async def create_slot(date: str, status: str = "open") -> dict:
    row = await db_module.fetch_one(
        "INSERT INTO slots (data) VALUES ($1::jsonb) RETURNING id, data",
        f'{{"date": "{date}", "status": "{status}", "cancelled_reason": null, "nudge_sent": false, "details": {{}}}}'
    )
    return {"id": row["id"], **row["data"]}


async def login(client, username: str, pin: str = "1234"):
    """Helper to log in and return client with session cookie."""
    await client.post("/login", data={"username": username, "pin": pin})
```

- [ ] **Step 2: Verify test DB is accessible**

```bash
createdb -U soccer -h localhost soccerbooking_test 2>/dev/null || true
DATABASE_URL=postgresql://soccer:soccer@localhost:5432/soccerbooking_test pytest tests/ --collect-only
```

Expected: collected 0 items (no errors)

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: test infrastructure and DB fixtures"
```

---

## Task 4: Slot Utilities

**Files:**
- Create: `backend/slot_utils.py`
- Test: `tests/test_slot_utils.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_slot_utils.py
from datetime import datetime, date
import pytest
from zoneinfo import ZoneInfo
from backend.slot_utils import (
    compute_slot_state,
    next_wednesday,
    SlotState,
)
from tests.conftest import create_slot


TZ = ZoneInfo("Europe/Paris")


def paris(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=TZ)


class TestNextWednesday:
    def test_returns_next_wednesday_from_monday(self):
        # Monday 2026-03-23
        result = next_wednesday(date(2026, 3, 23))
        assert result == date(2026, 3, 25)

    def test_returns_same_wednesday_if_today_is_wednesday(self):
        result = next_wednesday(date(2026, 3, 25))
        assert result == date(2026, 3, 25)

    def test_returns_next_wednesday_from_thursday(self):
        result = next_wednesday(date(2026, 3, 26))
        assert result == date(2026, 4, 1)


class TestComputeSlotState:
    def test_open_monday_afternoon(self):
        slot = {"date": "2026-03-25", "status": "open"}
        now = paris(2026, 3, 23, 14)  # Monday 14:00
        assert compute_slot_state(slot, now) == SlotState.OPEN

    def test_open_wednesday_morning(self):
        slot = {"date": "2026-03-25", "status": "open"}
        now = paris(2026, 3, 25, 10)  # Wednesday 10:00
        assert compute_slot_state(slot, now) == SlotState.OPEN

    def test_closed_wednesday_18_to_19(self):
        slot = {"date": "2026-03-25", "status": "open"}
        now = paris(2026, 3, 25, 18, 30)  # Wednesday 18:30
        assert compute_slot_state(slot, now) == SlotState.CLOSED

    def test_frozen_wednesday_after_19(self):
        slot = {"date": "2026-03-25", "status": "open"}
        now = paris(2026, 3, 25, 20)  # Wednesday 20:00
        assert compute_slot_state(slot, now) == SlotState.FROZEN

    def test_frozen_sunday(self):
        slot = {"date": "2026-03-25", "status": "open"}
        now = paris(2026, 3, 29, 12)  # Sunday
        assert compute_slot_state(slot, now) == SlotState.FROZEN

    def test_cancelled_overrides_time_state(self):
        slot = {"date": "2026-03-25", "status": "cancelled"}
        now = paris(2026, 3, 23, 14)  # Monday OPEN window
        assert compute_slot_state(slot, now) == SlotState.CANCELLED

    def test_boundary_exactly_18h_is_closed(self):
        slot = {"date": "2026-03-25", "status": "open"}
        now = paris(2026, 3, 25, 18, 0)
        assert compute_slot_state(slot, now) == SlotState.CLOSED

    def test_boundary_exactly_19h_is_frozen(self):
        slot = {"date": "2026-03-25", "status": "open"}
        now = paris(2026, 3, 25, 19, 0)
        assert compute_slot_state(slot, now) == SlotState.FROZEN

    def test_before_monday_noon_is_frozen(self):
        slot = {"date": "2026-03-25", "status": "open"}
        now = paris(2026, 3, 23, 11, 59)  # Monday before noon
        assert compute_slot_state(slot, now) == SlotState.FROZEN


class TestGetOrCreateUpcomingSlot:
    async def test_creates_slot_if_none_exists(self):
        from backend.slot_utils import get_or_create_upcoming_slot
        now = paris(2026, 3, 23, 14)  # Monday after noon
        slot = await get_or_create_upcoming_slot(now)
        assert slot is not None
        assert slot["date"] == "2026-03-25"
        assert slot["status"] == "open"

    async def test_returns_existing_slot(self):
        from backend.slot_utils import get_or_create_upcoming_slot
        await create_slot("2026-03-25")
        now = paris(2026, 3, 23, 14)
        slot = await get_or_create_upcoming_slot(now)
        assert slot["date"] == "2026-03-25"

    async def test_returns_none_before_monday_noon(self):
        from backend.slot_utils import get_or_create_upcoming_slot
        now = paris(2026, 3, 23, 11)  # Monday before noon
        slot = await get_or_create_upcoming_slot(now)
        assert slot is None

    async def test_concurrent_creation_is_idempotent(self):
        """Duplicate insert should be silently ignored (unique index)."""
        import asyncio
        from backend.slot_utils import get_or_create_upcoming_slot
        now = paris(2026, 3, 23, 14)
        slots = await asyncio.gather(
            get_or_create_upcoming_slot(now),
            get_or_create_upcoming_slot(now),
            get_or_create_upcoming_slot(now),
        )
        from backend import db as db_module
        count = await db_module.fetch_val("SELECT COUNT(*) FROM slots")
        assert count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_slot_utils.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `slot_utils` doesn't exist yet.

- [ ] **Step 3: Implement `backend/slot_utils.py`**

```python
from datetime import datetime, date, timedelta
from enum import Enum
from zoneinfo import ZoneInfo
import asyncpg

from backend import db as db_module
from backend.config import TIMEZONE


class SlotState(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    FROZEN = "frozen"
    CANCELLED = "cancelled"


def next_wednesday(from_date: date) -> date:
    """Return the next Wednesday on or after from_date."""
    days_ahead = (2 - from_date.weekday()) % 7  # Wednesday = 2
    return from_date + timedelta(days=days_ahead)


def compute_slot_state(slot: dict, now: datetime) -> SlotState:
    """Derive slot state from slot data and current time."""
    if slot["status"] == "cancelled":
        return SlotState.CANCELLED

    tz = ZoneInfo(TIMEZONE)
    slot_date = date.fromisoformat(slot["date"])
    wednesday = datetime(slot_date.year, slot_date.month, slot_date.day, tzinfo=tz)
    monday = wednesday - timedelta(days=2)

    monday_noon = monday.replace(hour=12, minute=0, second=0, microsecond=0)
    wednesday_18h = wednesday.replace(hour=18, minute=0, second=0, microsecond=0)
    wednesday_19h = wednesday.replace(hour=19, minute=0, second=0, microsecond=0)

    if now < monday_noon:
        return SlotState.FROZEN
    if now < wednesday_18h:
        return SlotState.OPEN
    if now < wednesday_19h:
        return SlotState.CLOSED
    return SlotState.FROZEN


async def get_or_create_upcoming_slot(now: datetime) -> dict | None:
    """Return the upcoming slot, creating it if Monday >= noon and it doesn't exist."""
    tz = ZoneInfo(TIMEZONE)
    today = now.date()
    wednesday = next_wednesday(today)
    monday = wednesday - timedelta(days=2)
    monday_noon = datetime(monday.year, monday.month, monday.day, 12, tzinfo=tz)

    if now < monday_noon:
        return None

    date_str = wednesday.isoformat()
    # Try to fetch existing
    row = await db_module.fetch_one(
        "SELECT id, data FROM slots WHERE data->>'date' = $1", date_str
    )
    if row:
        return {"id": row["id"], **row["data"]}

    # Insert — ignore duplicate (concurrent request)
    try:
        import json
        data = json.dumps({
            "date": date_str,
            "status": "open",
            "cancelled_reason": None,
            "nudge_sent": False,
            "details": {},
        })
        row = await db_module.fetch_one(
            "INSERT INTO slots (data) VALUES ($1::jsonb) RETURNING id, data", data
        )
        return {"id": row["id"], **row["data"]}
    except asyncpg.UniqueViolationError:
        row = await db_module.fetch_one(
            "SELECT id, data FROM slots WHERE data->>'date' = $1", date_str
        )
        return {"id": row["id"], **row["data"]}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_slot_utils.py -v
```

Expected: all green

- [ ] **Step 5: Commit**

```bash
git add backend/slot_utils.py tests/test_slot_utils.py
git commit -m "feat: slot utilities with lifecycle state computation"
```

---

## Task 5: Booking Utilities & Webhooks

**Files:**
- Create: `backend/webhooks.py`
- Create: `backend/booking_utils.py`
- Test: `tests/test_booking_utils.py`

- [ ] **Step 1: Create `backend/webhooks.py`**

```python
import httpx
from backend.config import WEBHOOK_URL


async def fire_waitlist_promoted(
    slot_date: str, booking: dict, booked_by_username: str, player_username: str | None = None
) -> None:
    if not WEBHOOK_URL:
        return
    # For player bookings: username is the player's own username (from user_id lookup)
    # For guest bookings: username is null (guest has no user row)
    payload = {
        "event": "waitlist_promoted",
        "slot_date": slot_date,
        "type": booking["type"],
        "user_id": booking.get("user_id"),
        "username": player_username if booking["type"] == "player" else None,
        "guest_name": booking.get("guest_name"),
        "booked_by_id": booking["booked_by_id"],
        "booked_by_username": booked_by_username,
    }
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(WEBHOOK_URL, json=payload)
    except Exception:
        pass  # fire-and-forget


async def fire_slot_not_full(slot_date: str, confirmed_count: int) -> None:
    if not WEBHOOK_URL:
        return
    payload = {
        "event": "slot_not_full",
        "slot_date": slot_date,
        "confirmed_count": confirmed_count,
        "spots_remaining": 10 - confirmed_count,
    }
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(WEBHOOK_URL, json=payload)
    except Exception:
        pass
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_booking_utils.py
import json
import pytest
from tests.conftest import create_user, create_slot
from backend.booking_utils import (
    create_booking,
    cancel_booking,
    get_slot_bookings,
    BookingError,
)
from backend import db as db_module


async def _make_booking(slot_id, user_id, booked_by_id, btype="player", guest_name=None):
    return await create_booking(
        slot_id=slot_id,
        user_id=user_id,
        booked_by_id=booked_by_id,
        booking_type=btype,
        guest_name=guest_name,
    )


class TestCreateBooking:
    async def test_first_booking_is_confirmed(self):
        user = await create_user("alice")
        slot = await create_slot("2026-03-25")
        b = await _make_booking(slot["id"], user["id"], user["id"])
        assert b["status"] == "confirmed"
        assert b["position"] == 1

    async def test_position_increments(self):
        slot = await create_slot("2026-03-25")
        users = [await create_user(f"u{i}") for i in range(3)]
        bookings = [await _make_booking(slot["id"], u["id"], u["id"]) for u in users]
        assert [b["position"] for b in bookings] == [1, 2, 3]

    async def test_eleventh_booking_goes_to_waitlist(self):
        slot = await create_slot("2026-03-25")
        users = [await create_user(f"u{i}") for i in range(11)]
        bookings = [await _make_booking(slot["id"], u["id"], u["id"]) for u in users]
        assert bookings[-1]["status"] == "waitlist"

    async def test_max_waitlist_raises(self):
        slot = await create_slot("2026-03-25")
        users = [await create_user(f"u{i}") for i in range(13)]
        for u in users[:12]:
            await _make_booking(slot["id"], u["id"], u["id"])
        with pytest.raises(BookingError, match="full"):
            await _make_booking(slot["id"], users[12]["id"], users[12]["id"])

    async def test_duplicate_player_booking_raises(self):
        user = await create_user("alice")
        slot = await create_slot("2026-03-25")
        await _make_booking(slot["id"], user["id"], user["id"])
        with pytest.raises(BookingError, match="already booked"):
            await _make_booking(slot["id"], user["id"], user["id"])

    async def test_player_can_add_guest(self):
        player = await create_user("alice")
        slot = await create_slot("2026-03-25")
        g = await _make_booking(slot["id"], None, player["id"], "guest", "Bob Guest")
        assert g["type"] == "guest"
        assert g["guest_name"] == "Bob Guest"
        assert g["user_id"] is None

    async def test_guest_requires_name(self):
        player = await create_user("alice")
        slot = await create_slot("2026-03-25")
        with pytest.raises(BookingError, match="guest_name"):
            await _make_booking(slot["id"], None, player["id"], "guest", None)


class TestCancelBooking:
    async def test_cancel_confirmed_promotes_waitlist(self):
        slot = await create_slot("2026-03-25")
        users = [await create_user(f"u{i}") for i in range(11)]
        bookings = [await _make_booking(slot["id"], u["id"], u["id"]) for u in users]
        waitlist_booking = bookings[-1]
        assert waitlist_booking["status"] == "waitlist"

        # Cancel first confirmed
        await cancel_booking(bookings[0]["id"], slot["id"])

        # Waitlist entry should now be confirmed
        row = await db_module.fetch_one(
            "SELECT data FROM bookings WHERE id = $1", waitlist_booking["id"]
        )
        assert row["data"]["status"] == "confirmed"

    async def test_cancel_confirmed_no_waitlist(self):
        slot = await create_slot("2026-03-25")
        user = await create_user("alice")
        b = await _make_booking(slot["id"], user["id"], user["id"])
        await cancel_booking(b["id"], slot["id"])
        row = await db_module.fetch_one("SELECT data FROM bookings WHERE id = $1", b["id"])
        assert row is None

    async def test_cancel_waitlist_no_promotion(self):
        slot = await create_slot("2026-03-25")
        users = [await create_user(f"u{i}") for i in range(11)]
        bookings = [await _make_booking(slot["id"], u["id"], u["id"]) for u in users]
        waitlist_b = bookings[-1]
        await cancel_booking(waitlist_b["id"], slot["id"])
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 10


class TestGetSlotBookings:
    async def test_returns_confirmed_and_waitlist(self):
        slot = await create_slot("2026-03-25")
        users = [await create_user(f"u{i}") for i in range(3)]
        for u in users:
            await _make_booking(slot["id"], u["id"], u["id"])
        result = await get_slot_bookings(slot["id"])
        assert len(result["confirmed"]) == 3
        assert len(result["waitlist"]) == 0
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_booking_utils.py -v
```

Expected: `ImportError`

- [ ] **Step 4: Implement `backend/booking_utils.py`**

```python
import json
from backend import db as db_module


class BookingError(Exception):
    pass


async def get_slot_bookings(slot_id: int) -> dict:
    """Return {"confirmed": [...], "waitlist": [...]} for a slot."""
    rows = await db_module.fetch_all(
        "SELECT id, data FROM bookings WHERE (data->>'slot_id')::int = $1 ORDER BY (data->>'position')::int",
        slot_id,
    )
    bookings = [{"id": r["id"], **r["data"]} for r in rows]
    return {
        "confirmed": [b for b in bookings if b["status"] == "confirmed"],
        "waitlist": [b for b in bookings if b["status"] == "waitlist"],
    }


async def create_booking(
    slot_id: int,
    user_id: int | None,
    booked_by_id: int,
    booking_type: str,
    guest_name: str | None = None,
) -> dict:
    if booking_type == "guest" and not guest_name:
        raise BookingError("guest_name required for guest bookings")

    pool = db_module.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Lock slot row to serialize position assignment
            await conn.fetchrow("SELECT id FROM slots WHERE id = $1 FOR UPDATE", slot_id)

            # Check for duplicate player booking
            if booking_type == "player" and user_id is not None:
                existing = await conn.fetchrow(
                    "SELECT id FROM bookings WHERE (data->>'slot_id')::int = $1 AND (data->>'user_id')::int = $2 AND data->>'type' = 'player'",
                    slot_id, user_id,
                )
                if existing:
                    raise BookingError("already booked")

            # Count confirmed and waitlist
            confirmed_count = await conn.fetchval(
                "SELECT COUNT(*) FROM bookings WHERE (data->>'slot_id')::int = $1 AND data->>'status' = 'confirmed'",
                slot_id,
            )
            waitlist_count = await conn.fetchval(
                "SELECT COUNT(*) FROM bookings WHERE (data->>'slot_id')::int = $1 AND data->>'status' = 'waitlist'",
                slot_id,
            )

            if confirmed_count >= 10 and waitlist_count >= 2:
                raise BookingError("slot and waitlist are full")

            status = "confirmed" if confirmed_count < 10 else "waitlist"

            # Assign position
            position = await conn.fetchval(
                "SELECT COALESCE(MAX((data->>'position')::int), 0) + 1 FROM bookings WHERE (data->>'slot_id')::int = $1",
                slot_id,
            )

            from datetime import datetime
            data = {
                "slot_id": slot_id,
                "user_id": user_id,
                "booked_by_id": booked_by_id,
                "type": booking_type,
                "guest_name": guest_name,
                "status": status,
                "position": position,
                "created_at": datetime.utcnow().isoformat(),
            }
            row = await conn.fetchrow(
                "INSERT INTO bookings (data) VALUES ($1::jsonb) RETURNING id, data",
                json.dumps(data),
            )
            return {"id": row["id"], **row["data"]}


async def cancel_booking(booking_id: int, slot_id: int) -> None:
    """Cancel a booking and promote the lowest-position waitlist entry if applicable."""
    pool = db_module.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Lock slot
            await conn.fetchrow("SELECT id FROM slots WHERE id = $1 FOR UPDATE", slot_id)

            row = await conn.fetchrow("SELECT data FROM bookings WHERE id = $1", booking_id)
            if not row:
                return
            booking = row["data"]
            was_confirmed = booking["status"] == "confirmed"

            # Delete the booking
            await conn.execute("DELETE FROM bookings WHERE id = $1", booking_id)

            # Promote lowest-position waitlist entry if confirmed was cancelled
            if was_confirmed:
                waitlist_row = await conn.fetchrow(
                    "SELECT id, data FROM bookings WHERE (data->>'slot_id')::int = $1 AND data->>'status' = 'waitlist' ORDER BY (data->>'position')::int LIMIT 1",
                    slot_id,
                )
                if waitlist_row:
                    import json as json_module
                    updated = dict(waitlist_row["data"])
                    updated["status"] = "confirmed"
                    await conn.execute(
                        "UPDATE bookings SET data = $1::jsonb WHERE id = $2",
                        json_module.dumps(updated),
                        waitlist_row["id"],
                    )
                    # Fire webhook after transaction (don't block)
                    return {"promoted": {"id": waitlist_row["id"], **updated}, "slot_id": slot_id}
    return None
```

Note: The webhook firing happens outside the transaction. Update `cancel_booking` to return promotion info and have callers fire webhooks. Adjust the implementation so the router calls `fire_waitlist_promoted` after `cancel_booking` returns.

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_booking_utils.py -v
```

Expected: all green

- [ ] **Step 6: Commit**

```bash
git add backend/booking_utils.py backend/webhooks.py tests/test_booking_utils.py
git commit -m "feat: booking utilities with waitlist promotion and webhooks"
```

---

## Task 6: Auth Utilities & FastAPI App Shell

**Files:**
- Create: `backend/auth.py`
- Create: `backend/main.py`
- Test: `tests/test_auth_routes.py`

- [ ] **Step 1: Create `backend/auth.py`**

```python
from fastapi import Request, HTTPException, status
from backend import db as db_module


async def get_current_user(request: Request) -> dict | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    row = await db_module.fetch_one("SELECT id, data FROM users WHERE id = $1", user_id)
    if not row:
        return None
    return {"id": row["id"], **row["data"]}


async def require_login(request: Request) -> dict:
    user = await get_current_user(request)
    if not user:
        from fastapi.responses import RedirectResponse
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user


async def require_admin(request: Request) -> dict:
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    if user.get("role") != "admin":
        raise HTTPException(status_code=302, headers={"Location": "/"})
    return user
```

- [ ] **Step 2: Create `backend/main.py`**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from backend.config import DATABASE_URL, SECRET_KEY, SESSION_MAX_AGE
from backend import db as db_module
from backend.routers import auth as auth_router
from backend.routers import main as main_router
from backend.routers import admin as admin_router
from backend.routers import profile as profile_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db_module.init_pool(DATABASE_URL)
    # Start scheduler
    from backend.scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    yield
    stop_scheduler()
    await db_module.close_pool()


app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=SESSION_MAX_AGE)
app.mount("/static", StaticFiles(directory="backend/static"), name="static")

app.include_router(auth_router.router)
app.include_router(main_router.router)
app.include_router(admin_router.router)
app.include_router(profile_router.router)

templates = Jinja2Templates(directory="backend/templates")
```

- [ ] **Step 3: Create stub routers** (so the app imports without error)

```python
# backend/routers/auth.py
from fastapi import APIRouter
router = APIRouter()

# backend/routers/main.py
from fastapi import APIRouter
router = APIRouter()

# backend/routers/admin.py
from fastapi import APIRouter
router = APIRouter()

# backend/routers/profile.py
from fastapi import APIRouter
router = APIRouter()
```

- [ ] **Step 4: Create stub scheduler**

```python
# backend/scheduler.py
def start_scheduler():
    pass

def stop_scheduler():
    pass
```

- [ ] **Step 5: Write failing auth route tests**

```python
# tests/test_auth_routes.py
import pytest
from tests.conftest import create_user, login


class TestRegister:
    async def test_get_register_returns_200(self, client):
        resp = await client.get("/register")
        assert resp.status_code == 200

    async def test_register_creates_user(self, client):
        resp = await client.post("/register", data={"username": "alice", "pin": "1234"})
        assert resp.status_code in (200, 302)
        from backend import db as db_module
        row = await db_module.fetch_one("SELECT data FROM users WHERE data->>'username' = 'alice'")
        assert row is not None

    async def test_register_duplicate_username_fails(self, client):
        await create_user("alice")
        resp = await client.post("/register", data={"username": "alice", "pin": "1234"})
        assert resp.status_code == 200
        assert b"already taken" in resp.content.lower() or b"taken" in resp.content.lower()

    async def test_register_pin_must_be_4_digits(self, client):
        resp = await client.post("/register", data={"username": "bob", "pin": "12"})
        assert resp.status_code == 200
        assert b"4" in resp.content or b"digit" in resp.content.lower()


class TestLogin:
    async def test_login_success_redirects(self, client):
        await create_user("alice", "1234")
        resp = await client.post("/login", data={"username": "alice", "pin": "1234"}, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"

    async def test_login_wrong_pin_fails(self, client):
        await create_user("alice", "1234")
        resp = await client.post("/login", data={"username": "alice", "pin": "9999"})
        assert resp.status_code == 200
        assert b"invalid" in resp.content.lower()

    async def test_login_unknown_user_fails(self, client):
        resp = await client.post("/login", data={"username": "nobody", "pin": "1234"})
        assert resp.status_code == 200
        assert b"invalid" in resp.content.lower()


class TestLogout:
    async def test_logout_clears_session(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.get("/logout", follow_redirects=False)
        assert resp.status_code == 302
        # After logout, / should redirect to login
        resp2 = await client.get("/", follow_redirects=False)
        assert resp2.status_code == 302
        assert "login" in resp2.headers["location"]
```

- [ ] **Step 6: Run tests to verify they fail**

```bash
pytest tests/test_auth_routes.py -v
```

Expected: failures (routes not implemented yet)

- [ ] **Step 7: Implement auth routes in `backend/routers/auth.py`**

```python
import json
from datetime import datetime
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from backend import db as db_module
import asyncpg

router = APIRouter()
templates = Jinja2Templates(directory="backend/templates")


@router.get("/register")
async def register_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@router.post("/register")
async def register_post(request: Request, username: str = Form(...), pin: str = Form(...)):
    error = None
    if not pin.isdigit() or len(pin) != 4:
        error = "PIN must be exactly 4 digits."
    if not username.strip():
        error = "Username is required."
    if not error:
        data = json.dumps({
            "username": username.strip(),
            "pin": pin,
            "role": "player",
            "created_at": datetime.utcnow().isoformat(),
        })
        try:
            await db_module.execute("INSERT INTO users (data) VALUES ($1::jsonb)", data)
            return RedirectResponse("/login", status_code=303)
        except asyncpg.UniqueViolationError:
            error = "Username already taken."
    return templates.TemplateResponse("register.html", {"request": request, "error": error}, status_code=400)


@router.get("/login")
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login_post(request: Request, username: str = Form(...), pin: str = Form(...)):
    row = await db_module.fetch_one(
        "SELECT id, data FROM users WHERE data->>'username' = $1", username
    )
    if not row or row["data"]["pin"] != pin:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid credentials."},
            status_code=401,
        )
    request.session["user_id"] = row["id"]
    return RedirectResponse("/", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
```

- [ ] **Step 8: Create minimal templates** (`backend/templates/base.html`, `login.html`, `register.html`)

```html
<!-- backend/templates/base.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SoccerBooking</title>
  <link rel="stylesheet" href="/static/css/main.css">
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
</head>
<body>
  {% block content %}{% endblock %}
</body>
</html>

<!-- backend/templates/login.html -->
{% extends "base.html" %}
{% block content %}
<main class="auth-page">
  <h1>Login</h1>
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
  <form method="post" action="/login">
    <input name="username" placeholder="Username" required>
    <input name="pin" type="password" placeholder="PIN (4 digits)" maxlength="4" pattern="\d{4}" required>
    <button type="submit">Login</button>
  </form>
  <p><a href="/register">Create account</a></p>
</main>
{% endblock %}

<!-- backend/templates/register.html -->
{% extends "base.html" %}
{% block content %}
<main class="auth-page">
  <h1>Register</h1>
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
  <form method="post" action="/register">
    <input name="username" placeholder="Username" required>
    <input name="pin" type="password" placeholder="PIN (4 digits)" maxlength="4" pattern="\d{4}" required>
    <button type="submit">Register</button>
  </form>
  <p><a href="/login">Already have an account?</a></p>
</main>
{% endblock %}
```

- [ ] **Step 9: Run tests to verify they pass**

```bash
pytest tests/test_auth_routes.py -v
```

Expected: all green

- [ ] **Step 10: Commit**

```bash
git add backend/auth.py backend/main.py backend/scheduler.py backend/routers/ backend/templates/
git commit -m "feat: auth routes (register, login, logout) and app shell"
```

---

## Task 7: Main Page (Read + Actions)

**Files:**
- Modify: `backend/routers/main.py`
- Create: `backend/templates/index.html`
- Create: `backend/templates/partials/slot_panel.html`
- Test: `tests/test_main_routes.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_main_routes.py
import pytest
from tests.conftest import create_user, create_slot, login
from backend.booking_utils import create_booking


class TestMainPage:
    async def test_unauthenticated_redirects_to_login(self, client):
        resp = await client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.headers["location"]

    async def test_authenticated_returns_200(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.get("/")
        assert resp.status_code == 200

    async def test_shows_slot_date(self, client):
        await create_user("alice", "1234")
        await create_slot("2026-03-25")
        await login(client, "alice")
        resp = await client.get("/")
        assert b"2026-03-25" in resp.content or b"March" in resp.content


class TestBookEndpoint:
    async def test_book_own_spot(self, client):
        user = await create_user("alice", "1234")
        slot = await create_slot("2026-03-25")
        await login(client, "alice")
        # Mock OPEN state by patching time
        from unittest.mock import patch
        from datetime import datetime
        from zoneinfo import ZoneInfo
        open_time = datetime(2026, 3, 23, 14, tzinfo=ZoneInfo("Europe/Paris"))
        with patch("backend.routers.main.datetime") as mock_dt:
            mock_dt.now.return_value = open_time
            resp = await client.post(f"/book", data={"slot_id": slot["id"], "type": "player"}, follow_redirects=False)
        assert resp.status_code in (200, 302)
        from backend import db as db_module
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 1

    async def test_book_returns_403_when_frozen(self, client):
        user = await create_user("alice", "1234")
        slot = await create_slot("2026-03-25")
        await login(client, "alice")
        from unittest.mock import patch
        from datetime import datetime
        from zoneinfo import ZoneInfo
        frozen_time = datetime(2026, 3, 25, 20, tzinfo=ZoneInfo("Europe/Paris"))
        with patch("backend.routers.main.datetime") as mock_dt:
            mock_dt.now.return_value = frozen_time
            resp = await client.post("/book", data={"slot_id": slot["id"], "type": "player"})
        assert resp.status_code == 403

    async def test_cancel_own_booking(self, client):
        user = await create_user("alice", "1234")
        slot = await create_slot("2026-03-25")
        booking = await create_booking(slot["id"], user["id"], user["id"], "player")
        await login(client, "alice")
        from unittest.mock import patch
        from datetime import datetime
        from zoneinfo import ZoneInfo
        open_time = datetime(2026, 3, 23, 14, tzinfo=ZoneInfo("Europe/Paris"))
        with patch("backend.routers.main.datetime") as mock_dt:
            mock_dt.now.return_value = open_time
            resp = await client.post("/cancel", data={"booking_id": booking["id"], "slot_id": slot["id"]})
        assert resp.status_code in (200, 302)
        from backend import db as db_module
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 0

    async def test_cannot_cancel_others_booking(self, client):
        alice = await create_user("alice", "1234")
        bob = await create_user("bob", "1234")
        slot = await create_slot("2026-03-25")
        booking = await create_booking(slot["id"], bob["id"], bob["id"], "player")
        await login(client, "alice")
        from unittest.mock import patch
        from datetime import datetime
        from zoneinfo import ZoneInfo
        open_time = datetime(2026, 3, 23, 14, tzinfo=ZoneInfo("Europe/Paris"))
        with patch("backend.routers.main.datetime") as mock_dt:
            mock_dt.now.return_value = open_time
            resp = await client.post("/cancel", data={"booking_id": booking["id"], "slot_id": slot["id"]})
        assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_main_routes.py -v
```

- [ ] **Step 3: Implement `backend/routers/main.py`**

```python
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from backend.auth import require_login
from backend.config import TIMEZONE
from backend.slot_utils import get_or_create_upcoming_slot, compute_slot_state, SlotState
from backend.booking_utils import create_booking, cancel_booking, get_slot_bookings, BookingError
from backend.webhooks import fire_waitlist_promoted
from backend import db as db_module

router = APIRouter()
templates = Jinja2Templates(directory="backend/templates")


def _now():
    return datetime.now(ZoneInfo(TIMEZONE))


@router.get("/")
async def index(request: Request, user: dict = Depends(require_login)):
    now = _now()
    slot = await get_or_create_upcoming_slot(now)
    context = {"request": request, "user": user, "slot": None, "bookings": None, "state": None}
    if slot:
        state = compute_slot_state(slot, now)
        slot_bookings = await get_slot_bookings(slot["id"])
        bookings_with_names = await _enrich_bookings(slot_bookings)
        context.update({"slot": slot, "state": state, "bookings": bookings_with_names})
    return templates.TemplateResponse("index.html", context)


@router.post("/book")
async def book(
    request: Request,
    slot_id: int = Form(...),
    booking_type: str = Form(...),
    guest_name: str = Form(None),
    user: dict = Depends(require_login),
):
    now = _now()
    slot = await db_module.fetch_one("SELECT id, data FROM slots WHERE id = $1", slot_id)
    if not slot:
        raise HTTPException(404)
    slot_dict = {"id": slot["id"], **slot["data"]}
    state = compute_slot_state(slot_dict, now)

    if state not in (SlotState.OPEN,):
        raise HTTPException(403, "Booking not allowed in current state")
    if slot_dict["status"] == "cancelled":
        raise HTTPException(403, "Slot is cancelled")

    user_id = user["id"] if booking_type == "player" else None
    try:
        await create_booking(slot_id, user_id, user["id"], booking_type, guest_name)
    except BookingError as e:
        raise HTTPException(400, str(e))

    # Return HTMX partial
    slot_bookings = await get_slot_bookings(slot_id)
    enriched = await _enrich_bookings(slot_bookings)
    return templates.TemplateResponse(
        "partials/slot_panel.html",
        {"request": request, "user": user, "slot": slot_dict, "state": state, "bookings": enriched},
    )


@router.post("/cancel")
async def cancel(
    request: Request,
    booking_id: int = Form(...),
    slot_id: int = Form(...),
    user: dict = Depends(require_login),
):
    now = _now()
    slot = await db_module.fetch_one("SELECT id, data FROM slots WHERE id = $1", slot_id)
    if not slot:
        raise HTTPException(404)
    slot_dict = {"id": slot["id"], **slot["data"]}
    state = compute_slot_state(slot_dict, now)

    if state not in (SlotState.OPEN,):
        raise HTTPException(403)

    # Verify ownership: user must be booked_by_id
    booking_row = await db_module.fetch_one("SELECT id, data FROM bookings WHERE id = $1", booking_id)
    if not booking_row:
        raise HTTPException(404)
    if booking_row["data"]["booked_by_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403)

    result = await cancel_booking(booking_id, slot_id)
    if result and result.get("promoted"):
        promoted = result["promoted"]
        by_row = await db_module.fetch_one(
            "SELECT data FROM users WHERE id = $1", promoted["booked_by_id"]
        )
        booked_by_username = by_row["data"]["username"] if by_row else ""
        # Resolve the promoted player's own username (None for guest bookings)
        player_username = None
        if promoted["type"] == "player" and promoted.get("user_id"):
            p_row = await db_module.fetch_one(
                "SELECT data FROM users WHERE id = $1", promoted["user_id"]
            )
            player_username = p_row["data"]["username"] if p_row else None
        await fire_waitlist_promoted(slot_dict["date"], promoted, booked_by_username, player_username)

    slot_bookings = await get_slot_bookings(slot_id)
    enriched = await _enrich_bookings(slot_bookings)
    return templates.TemplateResponse(
        "partials/slot_panel.html",
        {"request": request, "user": user, "slot": slot_dict, "state": state, "bookings": enriched},
    )


async def _enrich_bookings(slot_bookings: dict) -> dict:
    """Resolve booked_by_username for all bookings."""
    all_bookings = slot_bookings["confirmed"] + slot_bookings["waitlist"]
    user_ids = list({b["booked_by_id"] for b in all_bookings if b.get("booked_by_id")})
    users = {}
    for uid in user_ids:
        row = await db_module.fetch_one("SELECT id, data FROM users WHERE id = $1", uid)
        if row:
            users[uid] = row["data"]["username"]

    def enrich(b):
        return {**b, "booked_by_username": users.get(b.get("booked_by_id"), "?")}

    return {
        "confirmed": [enrich(b) for b in slot_bookings["confirmed"]],
        "waitlist": [enrich(b) for b in slot_bookings["waitlist"]],
    }
```

- [ ] **Step 4: Create templates**

Create `backend/templates/index.html`:
```html
{% extends "base.html" %}
{% block content %}
<main class="main-page">
  <header class="page-header">
    <h1>Soccer ⚽</h1>
    <nav><a href="/profile">Profile</a> · <a href="/logout">Logout</a></nav>
  </header>
  <div id="slot-panel" hx-get="/slot-panel" hx-trigger="load">
    {% include "partials/slot_panel.html" %}
  </div>
</main>
{% endblock %}
```

Create `backend/templates/partials/slot_panel.html`:
```html
{% if not slot %}
<section class="slot-card">
  <p>No upcoming slot yet. Check back Monday at noon.</p>
</section>
{% elif state.value == "cancelled" %}
<section class="slot-card cancelled">
  <h2>{{ slot.date }} — CANCELLED</h2>
  {% if slot.cancelled_reason %}<p>{{ slot.cancelled_reason }}</p>{% endif %}
</section>
{% else %}
<section class="slot-card">
  <h2>{{ slot.date }}</h2>
  <p class="state-badge state-{{ state.value }}">{{ state.value | upper }}</p>
  <p>{{ bookings.confirmed | length }} / 10 confirmed</p>

  <ol class="player-list">
    {% for i in range(10) %}
    <li>
      {% if i < bookings.confirmed | length %}
        {% set b = bookings.confirmed[i] %}
        {% if b.type == "guest" %}
          {{ b.guest_name }} (invited by {{ b.booked_by_username }})
        {% else %}
          {{ b.booked_by_username }}
        {% endif %}
      {% else %}
        —
      {% endif %}
    </li>
    {% endfor %}
  </ol>

  {% if bookings.waitlist %}
  <div class="waitlist">
    <h3>Waitlist</h3>
    <ol>
    {% for b in bookings.waitlist %}
      <li>
        {% if b.type == "guest" %}{{ b.guest_name }} (invited by {{ b.booked_by_username }})
        {% else %}{{ b.booked_by_username }}{% endif %}
      </li>
    {% endfor %}
    </ol>
  </div>
  {% endif %}

  {% if state.value == "open" %}
  <div class="actions">
    {% set my_player_booking = bookings.confirmed | selectattr("user_id", "equalto", user.id) | list %}
    {% set my_player_booking = my_player_booking + (bookings.waitlist | selectattr("user_id", "equalto", user.id) | list) %}
    {% set my_guest_booking = (bookings.confirmed + bookings.waitlist) | selectattr("booked_by_id", "equalto", user.id) | selectattr("type", "equalto", "guest") | list %}

    {% if not my_player_booking %}
    <form hx-post="/book" hx-target="#slot-panel" hx-swap="outerHTML">
      <input type="hidden" name="slot_id" value="{{ slot.id }}">
      <input type="hidden" name="type" value="player">
      <button type="submit">Book my spot</button>
    </form>
    {% else %}
    <form hx-post="/cancel" hx-target="#slot-panel" hx-swap="outerHTML">
      <input type="hidden" name="booking_id" value="{{ my_player_booking[0].id }}">
      <input type="hidden" name="slot_id" value="{{ slot.id }}">
      <button type="submit">Cancel my spot</button>
    </form>
    {% endif %}

    {% if not my_guest_booking %}
    <form hx-post="/book" hx-target="#slot-panel" hx-swap="outerHTML">
      <input type="hidden" name="slot_id" value="{{ slot.id }}">
      <input type="hidden" name="type" value="guest">
      <input name="guest_name" placeholder="Guest name" required>
      <button type="submit">Add a guest</button>
    </form>
    {% else %}
    <form hx-post="/cancel" hx-target="#slot-panel" hx-swap="outerHTML">
      <input type="hidden" name="booking_id" value="{{ my_guest_booking[0].id }}">
      <input type="hidden" name="slot_id" value="{{ slot.id }}">
      <button type="submit">Cancel my guest</button>
    </form>
    {% endif %}
  </div>
  {% endif %}
</section>
{% endif %}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_main_routes.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/routers/main.py backend/templates/index.html backend/templates/partials/
git commit -m "feat: main page with booking and cancellation"
```

---

## Task 8: APScheduler (Wednesday 14:00 Nudge)

**Files:**
- Modify: `backend/scheduler.py`

- [ ] **Step 1: Implement `backend/scheduler.py`**

```python
import asyncio
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.config import TIMEZONE

_scheduler: AsyncIOScheduler | None = None
logger = logging.getLogger(__name__)


async def _nudge_job():
    from backend import db as db_module
    from backend.webhooks import fire_slot_not_full
    import json

    tz = ZoneInfo(TIMEZONE)
    today = date.today()
    # Only run on Wednesdays
    if today.weekday() != 2:
        return

    date_str = today.isoformat()
    row = await db_module.fetch_one(
        "SELECT id, data FROM slots WHERE data->>'date' = $1", date_str
    )
    if not row:
        return

    slot = {"id": row["id"], **row["data"]}
    if slot["status"] != "open" or slot.get("nudge_sent"):
        return

    confirmed_count = await db_module.fetch_val(
        "SELECT COUNT(*) FROM bookings WHERE (data->>'slot_id')::int = $1 AND data->>'status' = 'confirmed'",
        slot["id"],
    )
    if confirmed_count >= 10:
        return

    await fire_slot_not_full(date_str, confirmed_count)

    updated = {**slot}
    updated.pop("id", None)
    updated["nudge_sent"] = True
    await db_module.execute(
        "UPDATE slots SET data = $1::jsonb WHERE id = $2",
        json.dumps(updated),
        slot["id"],
    )
    logger.info(f"Nudge sent for slot {date_str}, {confirmed_count} confirmed")


def start_scheduler():
    global _scheduler
    tz = ZoneInfo(TIMEZONE)
    _scheduler = AsyncIOScheduler(timezone=tz)
    _scheduler.add_job(
        _nudge_job,
        CronTrigger(day_of_week="wed", hour=14, minute=0, timezone=tz),
        id="wednesday_nudge",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler():
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
```

- [ ] **Step 2: Verify scheduler starts without error**

```bash
DATABASE_URL=postgresql://soccer:soccer@localhost:5432/soccerbooking SECRET_KEY=test python -c "
import asyncio
from backend.scheduler import start_scheduler, stop_scheduler
start_scheduler()
print('Scheduler OK')
stop_scheduler()
"
```

Expected: `Scheduler OK`

- [ ] **Step 3: Commit**

```bash
git add backend/scheduler.py
git commit -m "feat: APScheduler Wednesday 14:00 nudge job"
```

---

## Task 9: Admin Routes

**Files:**
- Modify: `backend/routers/admin.py`
- Create: `backend/templates/admin/index.html`
- Create: `backend/templates/admin/partials/booking_list.html`
- Create: `backend/templates/admin/partials/user_list.html`
- Test: `tests/test_admin_routes.py`

- [ ] **Step 1: Write failing admin tests**

```python
# tests/test_admin_routes.py
import pytest
from tests.conftest import create_user, create_slot, login
from backend.booking_utils import create_booking


class TestAdminAccess:
    async def test_non_admin_redirected(self, client):
        await create_user("alice", "1234", "player")
        await login(client, "alice")
        resp = await client.get("/admin", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"

    async def test_admin_can_access(self, client):
        await create_user("alice", "1234", "admin")
        await login(client, "alice")
        resp = await client.get("/admin")
        assert resp.status_code == 200


class TestAdminSlotManagement:
    async def test_cancel_slot(self, client):
        admin = await create_user("admin", "1234", "admin")
        slot = await create_slot("2026-03-25")
        await login(client, "admin")
        resp = await client.post("/admin/slot/cancel", data={
            "slot_id": slot["id"], "reason": "Holiday"
        })
        assert resp.status_code in (200, 302)
        from backend import db as db_module
        row = await db_module.fetch_one("SELECT data FROM slots WHERE id = $1", slot["id"])
        assert row["data"]["status"] == "cancelled"

    async def test_precancel_future_slot_creates_cancelled(self, client):
        admin = await create_user("admin", "1234", "admin")
        await login(client, "admin")
        resp = await client.post("/admin/slot/cancel", data={
            "date": "2026-04-01", "reason": "Easter"
        })
        assert resp.status_code in (200, 302)
        from backend import db as db_module
        row = await db_module.fetch_one("SELECT data FROM slots WHERE data->>'date' = '2026-04-01'")
        assert row is not None
        assert row["data"]["status"] == "cancelled"


class TestAdminBookingManagement:
    async def test_admin_can_cancel_any_booking(self, client):
        admin = await create_user("admin", "1234", "admin")
        player = await create_user("bob", "1234", "player")
        slot = await create_slot("2026-03-25")
        booking = await create_booking(slot["id"], player["id"], player["id"], "player")
        await login(client, "admin")
        from unittest.mock import patch
        from datetime import datetime
        from zoneinfo import ZoneInfo
        open_time = datetime(2026, 3, 23, 14, tzinfo=ZoneInfo("Europe/Paris"))
        with patch("backend.routers.admin.datetime") as mock_dt:
            mock_dt.now.return_value = open_time
            resp = await client.post("/admin/booking/cancel", data={
                "booking_id": booking["id"], "slot_id": slot["id"]
            })
        assert resp.status_code in (200, 302)
        from backend import db as db_module
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 0

    async def test_admin_can_add_player_by_username(self, client):
        admin = await create_user("admin", "1234", "admin")
        player = await create_user("bob", "1234", "player")
        slot = await create_slot("2026-03-25")
        await login(client, "admin")
        from unittest.mock import patch
        from datetime import datetime
        from zoneinfo import ZoneInfo
        open_time = datetime(2026, 3, 23, 14, tzinfo=ZoneInfo("Europe/Paris"))
        with patch("backend.routers.admin.datetime") as mock_dt:
            mock_dt.now.return_value = open_time
            resp = await client.post("/admin/booking/add", data={
                "slot_id": slot["id"], "username": "bob"
            })
        assert resp.status_code in (200, 302)
        from backend import db as db_module
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 1

    async def test_admin_can_cancel_during_closed(self, client):
        """Admins can cancel bookings during CLOSED (Wed 18:00-19:00)."""
        admin = await create_user("admin", "1234", "admin")
        player = await create_user("bob", "1234", "player")
        slot = await create_slot("2026-03-25")
        booking = await create_booking(slot["id"], player["id"], player["id"], "player")
        await login(client, "admin")
        from unittest.mock import patch
        from datetime import datetime
        from zoneinfo import ZoneInfo
        closed_time = datetime(2026, 3, 25, 18, 30, tzinfo=ZoneInfo("Europe/Paris"))
        with patch("backend.routers.admin.datetime") as mock_dt:
            mock_dt.now.return_value = closed_time
            resp = await client.post("/admin/booking/cancel", data={
                "booking_id": booking["id"], "slot_id": slot["id"]
            })
        assert resp.status_code in (200, 302)
        from backend import db as db_module
        count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert count == 0

    async def test_admin_cannot_cancel_during_frozen(self, client):
        """Nobody can cancel bookings during FROZEN (Wed 19:00 → Mon 12:00)."""
        admin = await create_user("admin", "1234", "admin")
        player = await create_user("bob", "1234", "player")
        slot = await create_slot("2026-03-25")
        booking = await create_booking(slot["id"], player["id"], player["id"], "player")
        await login(client, "admin")
        from unittest.mock import patch
        from datetime import datetime
        from zoneinfo import ZoneInfo
        frozen_time = datetime(2026, 3, 25, 20, tzinfo=ZoneInfo("Europe/Paris"))
        with patch("backend.routers.admin.datetime") as mock_dt:
            mock_dt.now.return_value = frozen_time
            resp = await client.post("/admin/booking/cancel", data={
                "booking_id": booking["id"], "slot_id": slot["id"]
            })
        assert resp.status_code == 403


class TestAdminUserManagement:
    async def test_reset_pin(self, client):
        admin = await create_user("admin", "1234", "admin")
        player = await create_user("bob", "1234", "player")
        await login(client, "admin")
        resp = await client.post("/admin/user/reset-pin", data={
            "user_id": player["id"], "new_pin": "5678"
        })
        assert resp.status_code in (200, 302)
        from backend import db as db_module
        row = await db_module.fetch_one("SELECT data FROM users WHERE id = $1", player["id"])
        assert row["data"]["pin"] == "5678"

    async def test_delete_user_cascades_bookings(self, client):
        admin = await create_user("admin", "1234", "admin")
        player = await create_user("bob", "1234", "player")
        slot = await create_slot("2026-03-25")
        await create_booking(slot["id"], player["id"], player["id"], "player")
        await login(client, "admin")
        resp = await client.post("/admin/user/delete", data={"user_id": player["id"]})
        assert resp.status_code in (200, 302)
        from backend import db as db_module
        user_row = await db_module.fetch_one("SELECT id FROM users WHERE id = $1", player["id"])
        assert user_row is None
        booking_count = await db_module.fetch_val("SELECT COUNT(*) FROM bookings")
        assert booking_count == 0

    async def test_promote_to_admin(self, client):
        admin = await create_user("admin", "1234", "admin")
        player = await create_user("bob", "1234", "player")
        await login(client, "admin")
        resp = await client.post("/admin/user/set-role", data={
            "user_id": player["id"], "role": "admin"
        })
        assert resp.status_code in (200, 302)
        from backend import db as db_module
        row = await db_module.fetch_one("SELECT data FROM users WHERE id = $1", player["id"])
        assert row["data"]["role"] == "admin"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_admin_routes.py -v
```

- [ ] **Step 3: Implement `backend/routers/admin.py`**

```python
import json
from datetime import datetime, date
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from backend.auth import require_admin
from backend.config import TIMEZONE
from backend.slot_utils import compute_slot_state, SlotState
from backend.booking_utils import create_booking, cancel_booking, get_slot_bookings, BookingError
from backend.webhooks import fire_waitlist_promoted
from backend import db as db_module

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="backend/templates")


def _now():
    return datetime.now(ZoneInfo(TIMEZONE))


@router.get("")
async def admin_index(request: Request, user: dict = Depends(require_admin)):
    now = _now()
    slots = await db_module.fetch_all(
        "SELECT id, data FROM slots ORDER BY data->>'date' DESC LIMIT 10"
    )
    slot_list = [{"id": r["id"], **r["data"]} for r in slots]
    users = await db_module.fetch_all("SELECT id, data FROM users ORDER BY id")
    user_list = [{"id": r["id"], **r["data"]} for r in users]

    current_slot = slot_list[0] if slot_list else None
    current_bookings = None
    if current_slot:
        current_bookings = await get_slot_bookings(current_slot["id"])

    return templates.TemplateResponse("admin/index.html", {
        "request": request,
        "user": user,
        "slots": slot_list,
        "current_slot": current_slot,
        "current_bookings": current_bookings,
        "users": user_list,
        "now": now,
    })


@router.post("/slot/cancel")
async def admin_cancel_slot(
    request: Request,
    user: dict = Depends(require_admin),
    slot_id: int = Form(None),
    date: str = Form(None),
    reason: str = Form(""),
):
    if slot_id:
        row = await db_module.fetch_one("SELECT id, data FROM slots WHERE id = $1", slot_id)
        if not row:
            raise HTTPException(404)
        updated = {**row["data"], "status": "cancelled", "cancelled_reason": reason}
        await db_module.execute(
            "UPDATE slots SET data = $1::jsonb WHERE id = $2",
            json.dumps(updated), slot_id
        )
    elif date:
        existing = await db_module.fetch_one(
            "SELECT id FROM slots WHERE data->>'date' = $1", date
        )
        if existing:
            row = await db_module.fetch_one("SELECT data FROM slots WHERE id = $1", existing["id"])
            updated = {**row["data"], "status": "cancelled", "cancelled_reason": reason}
            await db_module.execute(
                "UPDATE slots SET data = $1::jsonb WHERE id = $2",
                json.dumps(updated), existing["id"]
            )
        else:
            data = json.dumps({
                "date": date, "status": "cancelled",
                "cancelled_reason": reason, "nudge_sent": False, "details": {}
            })
            await db_module.execute("INSERT INTO slots (data) VALUES ($1::jsonb)", data)
    return RedirectResponse("/admin", status_code=303)


@router.post("/booking/cancel")
async def admin_cancel_booking(
    request: Request,
    booking_id: int = Form(...),
    slot_id: int = Form(...),
    user: dict = Depends(require_admin),
):
    now = _now()
    slot = await db_module.fetch_one("SELECT id, data FROM slots WHERE id = $1", slot_id)
    if not slot:
        raise HTTPException(404)
    slot_dict = {"id": slot["id"], **slot["data"]}
    state = compute_slot_state(slot_dict, now)
    # Admins can cancel during OPEN and CLOSED, but not FROZEN or CANCELLED
    if state not in (SlotState.OPEN, SlotState.CLOSED):
        raise HTTPException(403, "Cannot modify during FROZEN or CANCELLED state")

    result = await cancel_booking(booking_id, slot_id)
    if result and result.get("promoted"):
        promoted = result["promoted"]
        by_row = await db_module.fetch_one(
            "SELECT data FROM users WHERE id = $1", promoted["booked_by_id"]
        )
        booked_by_username = by_row["data"]["username"] if by_row else ""
        player_username = None
        if promoted["type"] == "player" and promoted.get("user_id"):
            p_row = await db_module.fetch_one(
                "SELECT data FROM users WHERE id = $1", promoted["user_id"]
            )
            player_username = p_row["data"]["username"] if p_row else None
        await fire_waitlist_promoted(slot_dict["date"], promoted, booked_by_username, player_username)

    return RedirectResponse("/admin", status_code=303)


@router.post("/booking/add")
async def admin_add_booking(
    request: Request,
    slot_id: int = Form(...),
    username: str = Form(...),
    user: dict = Depends(require_admin),
):
    now = _now()
    slot = await db_module.fetch_one("SELECT id, data FROM slots WHERE id = $1", slot_id)
    if not slot:
        raise HTTPException(404)
    slot_dict = {"id": slot["id"], **slot["data"]}
    state = compute_slot_state(slot_dict, now)
    # Admins can add during OPEN and CLOSED, but not FROZEN or CANCELLED
    if state not in (SlotState.OPEN, SlotState.CLOSED):
        raise HTTPException(403)

    player = await db_module.fetch_one(
        "SELECT id, data FROM users WHERE data->>'username' = $1", username
    )
    if not player:
        raise HTTPException(404, f"User {username} not found")

    try:
        await create_booking(slot_id, player["id"], user["id"], "player")
    except BookingError as e:
        raise HTTPException(400, str(e))

    return RedirectResponse("/admin", status_code=303)


@router.post("/user/reset-pin")
async def admin_reset_pin(
    request: Request,
    user_id: int = Form(...),
    new_pin: str = Form(...),
    user: dict = Depends(require_admin),
):
    if not new_pin.isdigit() or len(new_pin) != 4:
        raise HTTPException(400, "PIN must be 4 digits")
    row = await db_module.fetch_one("SELECT data FROM users WHERE id = $1", user_id)
    if not row:
        raise HTTPException(404)
    updated = {**row["data"], "pin": new_pin}
    await db_module.execute(
        "UPDATE users SET data = $1::jsonb WHERE id = $2",
        json.dumps(updated), user_id
    )
    return RedirectResponse("/admin", status_code=303)


@router.post("/user/delete")
async def admin_delete_user(
    request: Request,
    user_id: int = Form(...),
    user: dict = Depends(require_admin),
):
    # Cascade-delete confirmed/waitlist bookings on open/current slots, with promotion
    open_slots = await db_module.fetch_all(
        "SELECT id, data FROM slots WHERE data->>'status' = 'open'"
    )
    for slot_row in open_slots:
        slot_id = slot_row["id"]
        bookings = await db_module.fetch_all(
            "SELECT id, data FROM bookings WHERE (data->>'slot_id')::int = $1 AND (data->>'user_id')::int = $2",
            slot_id, user_id
        )
        for b_row in bookings:
            b = {"id": b_row["id"], **b_row["data"]}
            result = await cancel_booking(b["id"], slot_id)
            if result and result.get("promoted"):
                promoted = result["promoted"]
                by_row = await db_module.fetch_one(
                    "SELECT data FROM users WHERE id = $1", promoted["booked_by_id"]
                )
                booked_by_username = by_row["data"]["username"] if by_row else ""
                player_username = None
                if promoted["type"] == "player" and promoted.get("user_id"):
                    p_row = await db_module.fetch_one(
                        "SELECT data FROM users WHERE id = $1", promoted["user_id"]
                    )
                    player_username = p_row["data"]["username"] if p_row else None
                slot_data = {"id": slot_row["id"], **slot_row["data"]}
                await fire_waitlist_promoted(slot_data["date"], promoted, booked_by_username, player_username)

    await db_module.execute("DELETE FROM users WHERE id = $1", user_id)
    return RedirectResponse("/admin", status_code=303)


@router.post("/user/set-role")
async def admin_set_role(
    request: Request,
    user_id: int = Form(...),
    role: str = Form(...),
    user: dict = Depends(require_admin),
):
    if role not in ("player", "admin"):
        raise HTTPException(400)
    row = await db_module.fetch_one("SELECT data FROM users WHERE id = $1", user_id)
    if not row:
        raise HTTPException(404)
    updated = {**row["data"], "role": role}
    await db_module.execute(
        "UPDATE users SET data = $1::jsonb WHERE id = $2",
        json.dumps(updated), user_id
    )
    return RedirectResponse("/admin", status_code=303)
```

- [ ] **Step 4: Create admin templates**

Create `backend/templates/admin/index.html`:
```html
{% extends "base.html" %}
{% block content %}
<main class="admin-page">
  <header><h1>Admin Panel</h1><a href="/">← Back</a> · <a href="/logout">Logout</a></header>

  <section class="admin-section">
    <h2>Slot Management</h2>
    <form method="post" action="/admin/slot/cancel">
      <input type="date" name="date" placeholder="Date (YYYY-MM-DD)">
      <input name="reason" placeholder="Reason">
      <button type="submit">Cancel / Pre-cancel Slot</button>
    </form>
    {% if current_slot %}
    <p>Current slot: {{ current_slot.date }} — {{ current_slot.status }}</p>
    {% if current_slot.status != "cancelled" %}
    <form method="post" action="/admin/slot/cancel">
      <input type="hidden" name="slot_id" value="{{ current_slot.id }}">
      <input name="reason" placeholder="Reason">
      <button type="submit">Cancel this slot</button>
    </form>
    {% endif %}
    {% endif %}
  </section>

  {% if current_slot and current_bookings %}
  <section class="admin-section">
    <h2>Booking Management</h2>
    {% include "admin/partials/booking_list.html" %}
    <form method="post" action="/admin/booking/add">
      <input type="hidden" name="slot_id" value="{{ current_slot.id }}">
      <input name="username" placeholder="Username to add">
      <button type="submit">Add Player</button>
    </form>
  </section>
  {% endif %}

  <section class="admin-section">
    <h2>User Management</h2>
    {% include "admin/partials/user_list.html" %}
  </section>
</main>
{% endblock %}
```

Create `backend/templates/admin/partials/booking_list.html`:
```html
<ul class="admin-booking-list">
{% for b in current_bookings.confirmed + current_bookings.waitlist %}
<li>
  [{{ b.status }}] {% if b.type == "guest" %}{{ b.guest_name }} (guest){% else %}{{ b.booked_by_id }}{% endif %}
  <form method="post" action="/admin/booking/cancel" style="display:inline">
    <input type="hidden" name="booking_id" value="{{ b.id }}">
    <input type="hidden" name="slot_id" value="{{ current_slot.id }}">
    <button type="submit">✕</button>
  </form>
</li>
{% endfor %}
</ul>
```

Create `backend/templates/admin/partials/user_list.html`:
```html
<ul class="admin-user-list">
{% for u in users %}
<li>
  {{ u.username }} [{{ u.role }}]
  <form method="post" action="/admin/user/reset-pin" style="display:inline">
    <input type="hidden" name="user_id" value="{{ u.id }}">
    <input name="new_pin" placeholder="New PIN" maxlength="4" size="5">
    <button type="submit">Reset PIN</button>
  </form>
  <form method="post" action="/admin/user/set-role" style="display:inline">
    <input type="hidden" name="user_id" value="{{ u.id }}">
    <select name="role"><option value="player">player</option><option value="admin">admin</option></select>
    <button type="submit">Set Role</button>
  </form>
  <form method="post" action="/admin/user/delete" style="display:inline" onsubmit="return confirm('Delete {{ u.username }}?')">
    <input type="hidden" name="user_id" value="{{ u.id }}">
    <button type="submit">Delete</button>
  </form>
</li>
{% endfor %}
</ul>
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_admin_routes.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/routers/admin.py backend/templates/admin/
git commit -m "feat: admin panel (slot, booking, user management)"
```

---

## Task 10: Profile Page

**Files:**
- Modify: `backend/routers/profile.py`
- Create: `backend/templates/profile.html`
- Test: `tests/test_profile_routes.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_profile_routes.py
import pytest
from tests.conftest import create_user, login


class TestProfilePage:
    async def test_get_profile_returns_200(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.get("/profile")
        assert resp.status_code == 200

    async def test_change_pin_success(self, client):
        user = await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.post("/profile/pin", data={
            "current_pin": "1234", "new_pin": "5678", "confirm_pin": "5678"
        }, follow_redirects=False)
        assert resp.status_code in (200, 302)
        from backend import db as db_module
        row = await db_module.fetch_one("SELECT data FROM users WHERE id = $1", user["id"])
        assert row["data"]["pin"] == "5678"

    async def test_wrong_current_pin_fails(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.post("/profile/pin", data={
            "current_pin": "9999", "new_pin": "5678", "confirm_pin": "5678"
        })
        assert resp.status_code == 200
        assert b"incorrect" in resp.content.lower() or b"wrong" in resp.content.lower() or b"invalid" in resp.content.lower()

    async def test_pin_mismatch_fails(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.post("/profile/pin", data={
            "current_pin": "1234", "new_pin": "5678", "confirm_pin": "9999"
        })
        assert resp.status_code == 200
        assert b"match" in resp.content.lower()

    async def test_new_pin_must_be_4_digits(self, client):
        await create_user("alice", "1234")
        await login(client, "alice")
        resp = await client.post("/profile/pin", data={
            "current_pin": "1234", "new_pin": "12", "confirm_pin": "12"
        })
        assert resp.status_code == 200
        assert b"4" in resp.content or b"digit" in resp.content.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_profile_routes.py -v
```

- [ ] **Step 3: Implement `backend/routers/profile.py`**

```python
import json
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.auth import require_login
from backend import db as db_module

router = APIRouter()
templates = Jinja2Templates(directory="backend/templates")


@router.get("/profile")
async def profile_get(request: Request, user: dict = Depends(require_login)):
    return templates.TemplateResponse("profile.html", {"request": request, "user": user})


@router.post("/profile/pin")
async def profile_change_pin(
    request: Request,
    current_pin: str = Form(...),
    new_pin: str = Form(...),
    confirm_pin: str = Form(...),
    user: dict = Depends(require_login),
):
    error = None
    if user["pin"] != current_pin:
        error = "Current PIN is incorrect."
    elif not new_pin.isdigit() or len(new_pin) != 4:
        error = "New PIN must be exactly 4 digits."
    elif new_pin != confirm_pin:
        error = "PINs do not match."

    if error:
        return templates.TemplateResponse(
            "profile.html", {"request": request, "user": user, "error": error}, status_code=400
        )

    updated = {**{k: v for k, v in user.items() if k != "id"}, "pin": new_pin}
    await db_module.execute(
        "UPDATE users SET data = $1::jsonb WHERE id = $2",
        json.dumps(updated), user["id"]
    )
    return templates.TemplateResponse(
        "profile.html", {"request": request, "user": {**user, "pin": new_pin}, "success": "PIN updated successfully."}
    )
```

- [ ] **Step 4: Create `backend/templates/profile.html`**

```html
{% extends "base.html" %}
{% block content %}
<main class="auth-page">
  <header><h1>Profile</h1><a href="/">← Back</a></header>
  <h2>Change PIN</h2>
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
  {% if success %}<p class="success">{{ success }}</p>{% endif %}
  <form method="post" action="/profile/pin">
    <input type="password" name="current_pin" placeholder="Current PIN" maxlength="4" required>
    <input type="password" name="new_pin" placeholder="New PIN (4 digits)" maxlength="4" pattern="\d{4}" required>
    <input type="password" name="confirm_pin" placeholder="Confirm new PIN" maxlength="4" required>
    <button type="submit">Update PIN</button>
  </form>
</main>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_profile_routes.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/routers/profile.py backend/templates/profile.html tests/test_profile_routes.py
git commit -m "feat: profile page with PIN change"
```

---

## Task 11: Mobile-First CSS

**Files:**
- Create: `backend/static/css/main.css`

- [ ] **Step 1: Create `backend/static/css/main.css`**

```css
/* Reset & base */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --primary: #2d6a4f;
  --primary-light: #52b788;
  --danger: #e63946;
  --warn: #f4a261;
  --bg: #f8f9fa;
  --surface: #ffffff;
  --text: #212529;
  --muted: #6c757d;
  --radius: 8px;
  --shadow: 0 2px 8px rgba(0,0,0,.08);
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  font-size: 16px;
  line-height: 1.5;
}

/* Layout */
main { max-width: 480px; margin: 0 auto; padding: 1rem; }

/* Auth pages */
.auth-page { display: flex; flex-direction: column; gap: 1rem; padding: 2rem 1rem; }
.auth-page h1 { font-size: 1.75rem; color: var(--primary); }

/* Forms */
form { display: flex; flex-direction: column; gap: .75rem; }
input, select {
  width: 100%; padding: .75rem 1rem;
  border: 1.5px solid #dee2e6; border-radius: var(--radius);
  font-size: 1rem; background: var(--surface);
  transition: border-color .15s;
}
input:focus, select:focus { outline: none; border-color: var(--primary-light); }

button {
  padding: .75rem 1.5rem;
  background: var(--primary); color: #fff;
  border: none; border-radius: var(--radius);
  font-size: 1rem; font-weight: 600; cursor: pointer;
  transition: background .15s;
}
button:hover { background: var(--primary-light); }
button[type="submit"].danger { background: var(--danger); }

/* Feedback */
.error { color: var(--danger); padding: .5rem 1rem; background: #fff0f0; border-radius: var(--radius); }
.success { color: var(--primary); padding: .5rem 1rem; background: #f0fff4; border-radius: var(--radius); }

/* Main page */
.page-header { display: flex; justify-content: space-between; align-items: center; padding: .75rem 0; margin-bottom: 1rem; }
.page-header h1 { font-size: 1.5rem; }
.page-header nav a { color: var(--muted); text-decoration: none; font-size: .875rem; }
.page-header nav a:hover { color: var(--primary); }

/* Slot card */
.slot-card { background: var(--surface); border-radius: var(--radius); box-shadow: var(--shadow); padding: 1.25rem; }
.slot-card h2 { font-size: 1.25rem; margin-bottom: .5rem; }
.slot-card.cancelled { opacity: .7; }

/* State badge */
.state-badge { display: inline-block; padding: .2rem .75rem; border-radius: 999px; font-size: .75rem; font-weight: 700; letter-spacing: .05em; margin-bottom: .75rem; }
.state-open { background: #d8f3dc; color: var(--primary); }
.state-closed { background: #fff3cd; color: #856404; }
.state-frozen { background: #cfe2ff; color: #0a58ca; }
.state-cancelled { background: #f8d7da; color: #842029; }

/* Player list */
.player-list { list-style: decimal; padding-left: 1.5rem; margin: .75rem 0; }
.player-list li { padding: .35rem 0; border-bottom: 1px solid #f0f0f0; font-size: .9375rem; }
.player-list li:last-child { border-bottom: none; }

/* Waitlist */
.waitlist { margin-top: 1rem; }
.waitlist h3 { font-size: .875rem; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; margin-bottom: .5rem; }
.waitlist ol { padding-left: 1.25rem; font-size: .9rem; }

/* Actions */
.actions { margin-top: 1rem; display: flex; flex-direction: column; gap: .5rem; }
.actions form { flex-direction: row; flex-wrap: wrap; gap: .5rem; }
.actions input[name="guest_name"] { flex: 1; min-width: 120px; }
.actions button { flex-shrink: 0; }

/* Admin */
.admin-page header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; }
.admin-section { background: var(--surface); border-radius: var(--radius); box-shadow: var(--shadow); padding: 1rem; margin-bottom: 1rem; }
.admin-section h2 { font-size: 1rem; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin-bottom: .75rem; }
.admin-booking-list, .admin-user-list { list-style: none; }
.admin-booking-list li, .admin-user-list li { padding: .4rem 0; border-bottom: 1px solid #f0f0f0; display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; }
.admin-user-list form { margin: 0; flex-direction: row; gap: .25rem; }
.admin-user-list input { width: 70px; padding: .35rem .5rem; font-size: .875rem; }
.admin-user-list select { width: auto; padding: .35rem .5rem; font-size: .875rem; }
.admin-user-list button { padding: .35rem .75rem; font-size: .875rem; }

/* Links */
a { color: var(--primary); text-decoration: none; }
a:hover { text-decoration: underline; }

/* Responsive tightening below 375px */
@media (max-width: 374px) {
  main { padding: .75rem; }
  .actions form { flex-direction: column; }
}
```

- [ ] **Step 2: Verify the app loads without CSS errors**

```bash
python -c "import backend.main; print('app imports OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/static/css/main.css
git commit -m "feat: mobile-first CSS (375px baseline)"
```

---

## Task 12: Full Integration Smoke Test

- [ ] **Step 1: Run full test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: all tests green

- [ ] **Step 2: Start the app locally**

```bash
docker compose up -d db
DATABASE_URL=postgresql://soccer:soccer@localhost:5432/soccerbooking SECRET_KEY=dev-key uvicorn backend.main:app --reload
```

- [ ] **Step 3: Manual verification checklist**

- [ ] `/register` — create user, shows error on duplicate username
- [ ] `/login` — login, shows error on wrong PIN
- [ ] `/` — shows upcoming slot (or "no slot" before Monday noon)
- [ ] Book a player spot — appears in list, action changes to "Cancel"
- [ ] Add a guest — shows `"{name} (invited by {username})"`
- [ ] Cancel both — slot reverts
- [ ] `/profile` — change own PIN, verify login with new PIN
- [ ] `/admin` — cancel slot, add player, reset PIN, delete user, change role
- [ ] Pre-cancel a future slot by date

- [ ] **Step 4: Run migration against production DB**

```bash
docker compose run --rm app alembic upgrade head
```

- [ ] **Step 5: Final commit**

```bash
git add .
git commit -m "chore: integration verified, production ready"
```

---

## Running Tests

```bash
# All tests
pytest tests/ -v

# Single file
pytest tests/test_slot_utils.py -v

# With coverage
pytest tests/ --cov=backend --cov-report=term-missing
```

## Environment Setup (Local Dev)

```bash
# Start DB
docker compose up -d db

# Install deps
pip install -e ".[dev]"

# Apply migrations
DATABASE_URL=postgresql://soccer:soccer@localhost:5432/soccerbooking alembic upgrade head

# Run app
DATABASE_URL=postgresql://soccer:soccer@localhost:5432/soccerbooking \
SECRET_KEY=dev-secret \
uvicorn backend.main:app --reload

# Create test DB
createdb -U soccer -h localhost soccerbooking_test
```
