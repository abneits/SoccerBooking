# SoccerBooking

A web app to book a weekly soccer slot. Self-hosted on a local NUC.

## Stack

- **Backend**: Python + FastAPI
- **Templating**: Jinja2 (server-rendered HTML, no JS build step)
- **Frontend**: HTMX for dynamic interactions, plain CSS (mobile-first)
- **Database**: PostgreSQL — use JSONB fields where schema flexibility helps (e.g., player metadata, booking preferences)
- **Infrastructure**: Docker (Docker Compose for local orchestration)
- **VCS**: GitHub
- **Auth**: Session-based login (username + 4-digit PIN)

## Architecture

```
SoccerBooking/
├── backend/
│   ├── main.py           # FastAPI app entry point
│   ├── routers/          # One file per domain (bookings, users, slots)
│   ├── models/           # SQLAlchemy models
│   ├── templates/        # Jinja2 HTML templates
│   ├── static/           # CSS, icons
│   └── db.py             # DB session / engine setup
├── docker-compose.yml
├── .env.example
└── CLAUDE.md
```

## Commands

```bash
# Start all services
docker compose up -d

# Stop services
docker compose down

# View logs
docker compose logs -f backend

# Run DB migrations
docker compose exec backend alembic upgrade head

# Access psql
docker compose exec db psql -U postgres -d soccerbooking
```

## Database

- Use **PostgreSQL JSON/JSONB fields** for flexible or evolving data (e.g., slot metadata, participant lists, notifications config)
- Prefer JSONB over JSON for indexing support
- Example: a `slots` table with a `jsonb` `details` column for sport-specific info

## Code Style

- Keep code simple and readable — prefer clarity over cleverness
- One responsibility per file/module
- Use environment variables for all config (never hardcode credentials)
- All secrets via `.env` (gitignored), documented in `.env.example`

## Mobile UI

- Design mobile-first: minimum touch target 44px, readable without zooming
- Test at 375px width (iPhone SE baseline)
- Avoid hover-only interactions — everything must work on touch

## Environment Setup

Copy `.env.example` to `.env` and fill in values before running.

Required env vars:
- `DATABASE_URL` — PostgreSQL connection string
- `SECRET_KEY` — session/JWT secret

## Hosting

- Self-hosted on a local NUC via Docker Compose
- No cloud dependencies — all services run locally
- Expose via local network or reverse proxy (e.g., Nginx or Caddy)

## Auth Spec

- **Mechanism**: Server-side sessions via `itsdangerous` signed cookies (FastAPI + Starlette `SessionMiddleware`)
- **Credentials**: `username` (text) + `pin` (exactly 4 digits, stored as plain text in DB)
- **Users table**: `id`, `username`, `pin` (VARCHAR 4), `created_at`
- **Login flow**: POST form → validate username+pin against DB → set session cookie → redirect
- **Logout**: clear session → redirect to login
- **Protection**: all routes except `/login` require a valid session; redirect to `/login` if not authenticated
- **Registration**: public `/register` form (username + 4-digit PIN, no admin approval)

## Gotchas

- Docker Compose `depends_on` does not wait for DB to be ready — use a health check or retry logic in the backend
- JSONB queries use `->` / `->>` operators in raw SQL; SQLAlchemy has native JSONB support
- Mobile browsers cache aggressively — set appropriate cache headers for booking state changes
- HTMX partial responses: return only the HTML fragment being swapped, not the full page
- PIN is stored as plain text — intentional, local/personal project only
