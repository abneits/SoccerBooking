# SoccerBooking

A mobile-first web app to manage a weekly soccer slot. 10 players per game, every Wednesday at 7 PM. Players actively book each week. Self-hosted on a local NUC via Docker Compose, local network only.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 + FastAPI |
| Templating | Jinja2 (server-rendered, no JS build step) |
| Frontend | HTMX + plain CSS (mobile-first, 375px baseline) |
| Database | PostgreSQL 16 — 3-table JSONB schema |
| Auth | Session cookies via Starlette `SessionMiddleware` |
| Scheduler | APScheduler (Wednesday 14:00 nudge job) |
| Infrastructure | Docker + Docker Compose |

---

## Features

- **Weekly slot** — one Wednesday 7 PM game per week, auto-created Monday at noon
- **Booking** — players book their own spot or add a guest; max 10 confirmed + 2 waitlist
- **Waitlist promotion** — when a confirmed booking is cancelled, the lowest-position waitlist entry is automatically promoted
- **Slot lifecycle** — computed states: OPEN / CLOSED / FROZEN / CANCELLED (never stored, derived at request time)
- **Webhooks** — `waitlist_promoted` and `slot_not_full` events posted to a configurable URL
- **Admin panel** — cancel slots, manage bookings, manage users (PIN reset, role, delete)
- **PIN change** — players can update their own 4-digit PIN from the profile page
- **Mobile-first UI** — 44 px touch targets, works at 375 px width

### Slot lifecycle

```
Monday 12:00      Wednesday 18:00   Wednesday 19:00   Monday 12:00
     │                  │                 │                │
  [OPEN] ────────── [CLOSED] ────── [FROZEN] ────────── [OPEN next]
  Players + admins   Admins only      Read-only (all)
```

| State | Window | Who can book / cancel |
|---|---|---|
| OPEN | Mon 12:00 → Wed 18:00 | Players + admins |
| CLOSED | Wed 18:00 → Wed 19:00 | Admins only |
| FROZEN | Wed 19:00 → Mon 12:00 | Nobody |

---

## Project Structure

```
SoccerBooking/
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh            # Runs alembic upgrade head then starts uvicorn
├── pyproject.toml
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py
├── backend/
│   ├── main.py              # FastAPI app factory, middleware, router registration
│   ├── db.py                # asyncpg pool + query helpers
│   ├── config.py            # Settings from env vars
│   ├── auth.py              # require_login(), require_admin() dependencies
│   ├── slot_utils.py        # compute_slot_state(), get_or_create_upcoming_slot()
│   ├── booking_utils.py     # create_booking(), cancel_booking(), get_slot_bookings()
│   ├── webhooks.py          # fire_waitlist_promoted(), fire_slot_not_full()
│   ├── scheduler.py         # APScheduler Wednesday 14:00 job
│   ├── routers/
│   │   ├── auth.py          # /register, /login, /logout
│   │   ├── main.py          # /, /book, /cancel
│   │   ├── admin.py         # /admin and all /admin/* routes
│   │   └── profile.py       # /profile, /profile/pin
│   ├── templates/
│   │   ├── base.html
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── profile.html
│   │   ├── index.html
│   │   ├── partials/slot_panel.html
│   │   └── admin/
│   │       ├── index.html
│   │       └── partials/{booking_list,user_list}.html
│   └── static/css/main.css
├── tests/
│   ├── conftest.py
│   ├── test_slot_utils.py
│   ├── test_booking_utils.py
│   ├── test_auth_routes.py
│   ├── test_main_routes.py
│   ├── test_admin_routes.py
│   └── test_profile_routes.py
├── ASSUMPTIONS.md
└── .env.example
```

---

## Data Model

All tables use a single `data JSONB NOT NULL` column plus `id SERIAL PRIMARY KEY`. No DB-level foreign keys — referential integrity is enforced in application code.

### `users`
```json
{
  "username": "bastien",
  "pin": "1234",
  "role": "player",
  "created_at": "2026-03-23T10:00:00"
}
```
- `role`: `player` or `admin`
- `pin`: 4-digit string, plaintext (intentional for this private local project)
- Unique index on `(data->>'username')`

### `slots`
```json
{
  "date": "2026-03-25",
  "status": "open",
  "cancelled_reason": null,
  "nudge_sent": false,
  "details": {}
}
```
- `status`: `open` or `cancelled` only — CLOSED / FROZEN are computed at request time, never stored
- Unique index on `(data->>'date')`

### `bookings`
```json
{
  "slot_id": 1,
  "user_id": 3,
  "booked_by_id": 3,
  "type": "player",
  "guest_name": null,
  "status": "confirmed",
  "position": 4,
  "created_at": "2026-03-23T10:05:00"
}
```
- `type`: `player` or `guest`
- `status`: `confirmed` or `waitlist`
- `position`: immutable insertion counter — lower value = higher promotion priority
- `user_id`: null for guests (guests have no `users` row)
- `booked_by_id`: always the player who created the booking

---

## Routes

| Route | Access | Description |
|---|---|---|
| `GET /register` | Public | Registration form |
| `POST /register` | Public | Create account → redirect to `/login` |
| `GET /login` | Public | Login form |
| `POST /login` | Public | Authenticate → redirect to `/` |
| `GET /logout` | Player+ | Clear session → redirect to `/login` |
| `GET /` | Player+ | Main page — current slot + booking actions |
| `POST /book` | Player+ | Book a spot or add a guest (HTMX partial response) |
| `POST /cancel` | Player+ | Cancel own booking (HTMX partial response) |
| `GET /profile` | Player+ | PIN change form |
| `POST /profile/pin` | Player+ | Update own PIN |
| `GET /admin` | Admin | Admin panel |
| `POST /admin/slot/cancel` | Admin | Cancel or pre-cancel a slot by date |
| `POST /admin/booking/cancel` | Admin | Cancel any booking |
| `POST /admin/booking/add` | Admin | Add a registered player by username |
| `POST /admin/user/reset-pin` | Admin | Reset any user's PIN |
| `POST /admin/user/delete` | Admin | Delete user (cascade-deletes open slot bookings) |
| `POST /admin/user/set-role` | Admin | Promote or demote admin role |

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the required values.

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `SECRET_KEY` | Yes | — | Session signing key (use a long random string) |
| `WEBHOOK_URL` | No | `""` | HTTP POST target for webhook events (silent if unset) |
| `TIMEZONE` | No | `Europe/Paris` | Timezone for slot lifecycle and scheduler |
| `SESSION_MAX_AGE` | No | `604800` | Session duration in seconds (default: 7 days) |

---

## Deployment

### Prerequisites

- Docker and Docker Compose on the target server
- A PostgreSQL instance (or use the bundled `db` service in `docker-compose.yml`)

### Steps

```bash
# 1. Clone the repo
git clone <repo-url>
cd SoccerBooking

# 2. Configure environment
cp .env.example .env
# Edit .env — set DATABASE_URL and SECRET_KEY at minimum

# 3. Build and start
docker compose up -d --build
```

The app is available at `http://<server-ip>:8000`.

On first start, `entrypoint.sh` automatically runs `alembic upgrade head` to create the schema, then starts `uvicorn`. This is idempotent — safe on every container restart.

### Using an external database

Set `DATABASE_URL` to point to your external instance and remove the `db` service block from `docker-compose.yml`.

### Creating the first admin

Register a regular account at `/register`, then promote it directly in the database:

```sql
UPDATE users
SET data = data || '{"role": "admin"}'
WHERE data->>'username' = 'your_username';
```

---

## Local Development

```bash
# Install dependencies (including dev extras)
pip install -e ".[dev]"

# Start only the database
docker compose up -d db

# Run the app with auto-reload
DATABASE_URL=postgresql://soccer:soccer@localhost:5432/soccerbooking \
SECRET_KEY=dev-secret \
uvicorn backend.main:app --reload
```

---

## Running Tests

Tests require a real PostgreSQL instance — no mocking.

```bash
# Create the test database (first time only)
createdb -U soccer -h localhost soccerbooking_test

# Run all tests
DATABASE_URL=postgresql://soccer:soccer@localhost:5432/soccerbooking_test \
pytest tests/ -v

# Run a specific module
pytest tests/test_slot_utils.py -v

# With coverage report
pytest tests/ --cov=backend --cov-report=term-missing
```

Each test class gets a clean database state — tables are truncated before every test.

---

## Webhooks

All webhooks are HTTP POST to `WEBHOOK_URL`. Fire-and-forget — no retry on failure. Neither webhook fires if `WEBHOOK_URL` is empty.

### `waitlist_promoted`
Fires whenever a confirmed booking is cancelled and a waitlist entry is promoted.
```json
{
  "event": "waitlist_promoted",
  "slot_date": "2026-03-25",
  "type": "player",
  "user_id": 4,
  "username": "marc",
  "guest_name": null,
  "booked_by_id": 4,
  "booked_by_username": "marc"
}
```
For a guest booking: `user_id` and `username` are `null`; `guest_name` is set.

### `slot_not_full`
Fires Wednesday at 14:00 if the slot has fewer than 10 confirmed bookings.
```json
{
  "event": "slot_not_full",
  "slot_date": "2026-03-25",
  "confirmed_count": 7,
  "spots_remaining": 3
}
```

---

## Useful Commands

```bash
# View app logs
docker compose logs -f app

# Access PostgreSQL
docker compose exec db psql -U soccer -d soccerbooking

# Run a migration (e.g. after adding a new migration file)
docker compose exec app alembic upgrade head

# Stop services
docker compose down

# Stop and wipe the database volume
docker compose down -v
```

---

## Security Notes

- Registration is open to anyone on the network. Since the app is local-network-only (not internet-facing), this is acceptable.
- PIN is stored as plaintext — acceptable for a private local project with a trusted user base.
- `SECRET_KEY` must be a long random string in production. Never commit `.env` to version control.
