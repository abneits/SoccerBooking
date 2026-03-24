# SoccerBooking — Design Spec
**Date:** 2026-03-23
**Status:** Approved

---

## Overview

A mobile-first web app to manage a weekly soccer slot. 10 players per game, every Wednesday at 7PM. Players actively book each week. Self-hosted on a local NUC via Docker Compose, local network only.

---

## Stack

- **Backend**: Python + FastAPI
- **Templating**: Jinja2 (server-rendered, no JS build step)
- **Frontend**: HTMX + plain CSS (mobile-first, 375px baseline)
- **Database**: PostgreSQL — 3 tables, each with `id SERIAL PK` + `data JSONB`
- **Scheduler**: APScheduler (inside FastAPI, single Wednesday 14:00 job)
- **Auth**: Session cookies via Starlette `SessionMiddleware`

---

## Data Model

All tables use a single `data` JSONB column. No DB-level FK constraints — referential integrity enforced in application code. GIN index on each `data` column.

### `users`
```json
{
  "username": "bastien",
  "pin": "1234",
  "role": "admin",
  "created_at": "2026-03-23T10:00:00"
}
```
- `role`: `player` or `admin`
- `pin`: 4-digit string, stored as **plaintext** — intentional, local private project
- `username` must be unique — enforced via unique index on `(data->>'username')`

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
- `status`: `open` or `cancelled` only — **`closed` and `frozen` are not stored; they are computed states derived from the current time at request time** (see Slot Lifecycle)
- `nudge_sent`: true once the Wednesday 14:00 "not full" webhook has fired for this slot
- `details`: reserved for future metadata (currently unused)
- `date` must be unique — enforced via unique index on `(data->>'date')` to prevent duplicate slot creation

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
- `user_id`: the booked player's user id; **null for guests** (guests have no `users` row)
- `booked_by_id`: always the player who created the booking
- `guest_name`: null for player bookings; required non-empty string for guest bookings
- `position`: **immutable insertion counter** (auto-incremented per slot). Lower value = earlier in queue = higher promotion priority. Never updated after creation. Assigned at insert time via `SELECT COALESCE(MAX(position), 0) + 1 FROM bookings WHERE slot_id = ?` inside a transaction with a `SELECT ... FOR UPDATE` lock on the slot row, preventing race conditions under concurrent bookings.
- `booked_by_username` is **resolved at query time** by joining on `users.id = bookings.data->>'booked_by_id'`

**Display rule for guest entries:** `"{guest_name} (invited by {booked_by_username})"`

---

## Slot Lifecycle

```
Monday 12:00    Wednesday 14:00   Wednesday 18:00   Wednesday 19:00   Monday 12:00
     │                │                  │                 │                │
  [OPEN]────────[nudge webhook]────[CLOSED]──────────[FROZEN]──────────[OPEN next]
  Players book        │             Admin only        Read-only (all)
  and cancel          └─ fires if confirmed < 10
```

### Computed states (not stored in DB)

| State | Window | Who can modify |
|-------|--------|----------------|
| OPEN | Mon 12:00 → Wed 18:00 | Players + admins |
| CLOSED | Wed 18:00 → Wed 19:00 | Admins only |
| FROZEN | Wed 19:00 → Mon 12:00 | Nobody — true read-only |

State is **derived at request time** from `slot.data['date']` and the current timestamp:

```python
wednesday = slot_date  # the slot's Wednesday
if now < wednesday_18h:   → OPEN
elif now < wednesday_19h: → CLOSED  (admin only)
else:                     → FROZEN  (read-only for everyone)
```

The `status` field in the database only stores `open` (bookable) or `cancelled` (admin-cancelled). A slot with `status=cancelled` shows as cancelled regardless of the computed time-based state.

### Slot auto-creation

On any authenticated request, if no slot exists for the upcoming Wednesday AND `now >= monday_12h`: insert a new slot with `status=open`. The unique index on `(data->>'date')` makes this an effective upsert — concurrent requests silently ignore the duplicate insertion error and proceed.

### Wednesday 14:00 APScheduler job

Runs once per week (job registered at app startup, timezone-aware). Finds the slot for the current Wednesday. If `status=open` and confirmed bookings < 10 and `nudge_sent=false`: fires the `slot_not_full` webhook, sets `nudge_sent=true`.

---

## Booking Rules

- Max **10 confirmed** + **2 waitlist** per slot — shared across all booking types
- A player can book themselves, add a guest, or both — **independently**
- When a confirmed booking is cancelled → the booking with the **lowest `position`** among `waitlist` entries for that slot is promoted to `confirmed` → `waitlist_promoted` webhook fires
- A player can cancel their own booking and any guest booking where they are `booked_by_id`
- **OPEN**: players and admins can book and cancel
- **CLOSED**: only admins can cancel or add bookings
- **FROZEN**: nobody can modify bookings
- When a slot is `cancelled`: all bookings remain in DB for history; no booking actions are possible

---

## Roles & Permissions

| Action | Player | Admin |
|--------|--------|-------|
| Book own spot | ✅ (OPEN) | ✅ (OPEN + CLOSED) |
| Add own guest | ✅ (OPEN) | ✅ (OPEN + CLOSED) |
| Cancel own booking or own guest | ✅ (OPEN) | ✅ (OPEN + CLOSED) |
| Cancel any booking | ❌ | ✅ (OPEN + CLOSED) |
| Add any registered player | ❌ | ✅ (OPEN + CLOSED) |
| Cancel a slot | ❌ | ✅ |
| Pre-cancel future slot by date | ❌ | ✅ |
| Reset any user's PIN | ❌ | ✅ |
| Delete user | ❌ | ✅ |
| Promote/demote admin | ❌ | ✅ |

---

## Pages & Routes

| Route | Access | Description |
|-------|--------|-------------|
| `/register` | public | Self-registration (username + 4-digit PIN) |
| `/login` | public | Login form |
| `/logout` | player+ | Clears session cookie, redirects to `/login` |
| `/profile` | player+ | Change own PIN |
| `/` | player+ | Main page — current slot + booking actions |
| `/admin` | admin | Admin panel |

### Main page (`/`)

Single HTMX-powered page. Content:
- **Slot header**: date, computed state label, spots confirmed / 10
- **Confirmed list**: 10 numbered slots. Each entry: player username or `"{guest_name} (invited by {username})"`. Empty slots show as "—"
- **Waitlist section**: up to 2 entries shown below the confirmed list
- **My actions** (contextual based on computed state and user's booking status):
  - OPEN + not booked → "Book my spot" + "Add a guest"
  - OPEN + booked → "Cancel my spot"
  - OPEN + guest added → "Cancel my guest"
  - CLOSED / FROZEN / cancelled → read-only display, no action buttons

HTMX partial swaps refresh only the player list + action area on each action.

### Admin panel (`/admin`)

Three sections:
1. **Slot management**: date picker (Wednesdays only) → cancel with a reason; view current slot status. Pre-cancelling a future slot: if no row exists for that date, one is **created immediately** with `status=cancelled`; if it already exists, its `status` is updated to `cancelled`. Admins can cancel a slot in any state (OPEN, CLOSED, FROZEN, or future pre-cancel).
2. **Booking management**: full confirmed + waitlist list; cancel any entry; add any registered player by username. All booking modifications via `/admin` respect the OPEN/CLOSED/FROZEN rules — admins can act during OPEN and CLOSED, but not during FROZEN. The main page `/` is always player-facing and shows read-only during CLOSED and FROZEN for everyone including admins; admin booking actions are exclusively on `/admin`.
3. **User management**: list all users; reset PIN (admin sets new 4-digit PIN); delete user; promote/demote admin role. **Delete user rule**: if the user has any `confirmed` or `waitlist` bookings on a current or future open slot, those bookings are cascade-deleted at the application level before the user row is removed. If any cascade-deleted booking was `confirmed` and a waitlist entry exists for that slot, normal waitlist promotion applies (webhook fires).

### Auth
- `/register`: on success → redirect to `/login`
- `/login`: on success → redirect to `/`
- `/logout`: clears the session cookie (Starlette SessionMiddleware stores state in a signed client-side cookie — logout clears the cookie; no server-side session revocation is needed for this use case)
- Session duration: 7 days (configurable via `SESSION_MAX_AGE` env var)

---

## Webhooks

All webhooks are HTTP POST to `WEBHOOK_URL` env var. Fire-and-forget (no retry). Both types are independent events.

### `waitlist_promoted`
Fires on any confirmed booking cancellation when a waitlist entry exists.
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
For a guest: `user_id=null`, `type="guest"`, `guest_name="<name>"`, `booked_by_*` = inviting player.

### `slot_not_full`
Fires Wednesday 14:00 if open slot has fewer than 10 confirmed bookings.
```json
{
  "event": "slot_not_full",
  "slot_date": "2026-03-25",
  "confirmed_count": 7,
  "spots_remaining": 3
}
```

---

## Error Handling & Edge Cases

### Booking
| Scenario | Behaviour |
|----------|-----------|
| Book during CLOSED (non-admin) | Button hidden; direct POST → 403 |
| Book during FROZEN | Button hidden; direct POST → 403 |
| Book a cancelled slot | Slot shows cancelled, no action buttons |
| Player already has a booking of same type for this slot | 400 "already booked" |
| Confirmed full (10), waitlist not full | Booking goes to waitlist |
| Confirmed full + waitlist full (2) | 400 "slot and waitlist are full" |
| Confirmed booking cancelled, waitlist exists | Lowest-position waitlist entry promoted, webhook fires |
| Admin cancels slot with active bookings | `status=cancelled`, bookings kept in DB, slot read-only |
| Concurrent slot creation on Monday 12:00 | Unique index on date absorbs race — only one slot created |

### Auth
| Scenario | Behaviour |
|----------|-----------|
| Wrong username or PIN | "Invalid credentials" (no detail on which) |
| Session expired | Redirect to `/login` |
| Non-admin accesses `/admin` | Redirect to `/` |
| Duplicate username on register | "Username already taken" |
| PIN not exactly 4 digits | Client-side + server-side validation |

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | — |
| `SECRET_KEY` | Session signing key | — |
| `WEBHOOK_URL` | Target URL for all webhook POSTs | — |
| `TIMEZONE` | Timezone for slot lifecycle logic | `Europe/Paris` |
| `SESSION_MAX_AGE` | Session duration in seconds | `604800` (7 days) |

---

## Security Notes

- Registration is open to anyone with network access. Since the app is local-network-only (not internet-facing), this is acceptable.
- PIN is stored as plaintext — acceptable for a private local project.

---

## Profile Page (`/profile`)

Accessible to any logged-in player. Single action: **change own PIN**.

- Form: current PIN + new PIN (4 digits) + confirm new PIN
- Validation: current PIN must match DB; new PIN must be exactly 4 digits; confirm must match
- On success: PIN updated in DB, success message shown, user stays logged in
- Route: `GET /profile` (form) + `POST /profile/pin` (submit)

---

## Out of Scope

- Email / push notifications (webhook handles this externally)
- Player statistics or history pages
- Multiple concurrent slots per week
- Registration approval workflow
- Retry logic for webhook failures

---

## Generation Constraints

These rules apply to any agent or worker implementing this spec.

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
- Only pause and ask if a decision is a true blocker that cannot be reasonably inferred from this spec.
