import os

DATABASE_URL = os.environ["DATABASE_URL"]
SECRET_KEY = os.environ["SECRET_KEY"]
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
TIMEZONE = os.environ.get("TIMEZONE", "Europe/Paris")
SESSION_MAX_AGE = int(os.environ.get("SESSION_MAX_AGE", "604800"))

# Enable test-only endpoints (e.g. /internal/set-time). NEVER set to true in production.
TESTING = os.environ.get("TESTING", "false").lower() == "true"
