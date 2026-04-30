#!/bin/sh
set -e

echo "Waiting for PostgreSQL to be ready..."
until pg_isready -h "${DB_HOST:-db}" -U "${DB_USER:-soccer}" > /dev/null 2>&1; do
  sleep 1
done
echo "PostgreSQL is ready."

alembic upgrade head
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
