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
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            data JSONB NOT NULL
        )
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_username_idx ON users ((data->>'username'))")
    op.execute("CREATE INDEX IF NOT EXISTS users_data_gin ON users USING GIN (data)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS slots (
            id SERIAL PRIMARY KEY,
            data JSONB NOT NULL
        )
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS slots_date_idx ON slots ((data->>'date'))")
    op.execute("CREATE INDEX IF NOT EXISTS slots_data_gin ON slots USING GIN (data)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id SERIAL PRIMARY KEY,
            data JSONB NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS bookings_data_gin ON bookings USING GIN (data)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bookings")
    op.execute("DROP TABLE IF EXISTS slots")
    op.execute("DROP TABLE IF EXISTS users")
