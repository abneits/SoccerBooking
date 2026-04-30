#!/bin/sh
set -e

# Extract host and user from DATABASE_URL
# Format: postgresql://user:password@host:port/dbname
DB_HOST=$(echo "$DATABASE_URL" | sed 's|.*@\(.*\):\([0-9]*\)/.*|\1|')
DB_USER=$(echo "$DATABASE_URL" | sed 's|.*://\([^:]*\):.*|\1|')

echo "Waiting for PostgreSQL to be ready..."
until pg_isready -h "$DB_HOST" -U "$DB_USER" > /dev/null 2>&1; do
  sleep 1
done
echo "PostgreSQL is ready."

alembic upgrade head
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
