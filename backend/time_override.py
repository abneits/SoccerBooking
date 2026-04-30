"""
Shared time override for testing.

In production, _override is always None and get_now() returns the real time.
When TESTING=true, POST /internal/set-time sets _override; all routers and
slot_utils call get_now() instead of datetime.now() directly.
"""

from datetime import datetime
from zoneinfo import ZoneInfo
from backend.config import TIMEZONE

_override: datetime | None = None


def get_now() -> datetime:
    """Return the overridden time if set, otherwise the real current time."""
    if _override is not None:
        return _override
    return datetime.now(ZoneInfo(TIMEZONE))


def set_override(dt: datetime) -> None:
    global _override
    _override = dt


def reset_override() -> None:
    global _override
    _override = None
