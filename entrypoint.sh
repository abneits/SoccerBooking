#!/bin/sh
set -e

echo "Waiting for PostgreSQL to be ready..."
until python3 -c "
import psycopg2, os, sys
try:
    psycopg2.connect(os.environ['DATABASE_URL']).close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
  sleep 1
done
echo "PostgreSQL is ready."

alembic upgrade head
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
