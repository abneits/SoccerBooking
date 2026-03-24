# Project Scaffolding Assumptions

Assumptions made during Task 1 (Project Scaffolding) setup:

- **Docker Compose healthcheck**: A healthcheck was added for the `db` service, and `depends_on` uses `condition: service_healthy` for the `app` service. This prevents the known race condition documented in CLAUDE.md where `depends_on` alone does not wait for the database to be ready to accept connections.

- **WEBHOOK_URL default**: `WEBHOOK_URL` defaults to an empty string in `backend/config.py`. No webhook will be fired if the variable is not set in the environment.

- **SESSION_MAX_AGE default**: `SESSION_MAX_AGE` defaults to `604800` seconds (7 days). This can be overridden via the environment variable.

- **TIMEZONE default**: `TIMEZONE` defaults to `Europe/Paris`, reflecting the project's expected deployment locale.

- **entrypoint.sh uses `exec`**: The `exec` call replaces the shell process with the uvicorn process. This ensures Docker signals (e.g., SIGTERM on `docker compose stop`) are delivered directly to uvicorn rather than being caught by the shell wrapper.

- **No `--reload` flag in production**: The `entrypoint.sh` does not use `--reload`. Hot-reload is a development convenience and should not run in production. A bind-mount volume in `docker-compose.yml` is available for local development iteration without needing `--reload`.

- **`alembic/versions/` pre-created**: The directory is created upfront to avoid errors when running `alembic revision` for the first time, which expects the versions directory to already exist.
