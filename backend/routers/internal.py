"""
Internal test-only endpoints. Registered only when TESTING=true.
NEVER expose in production.

POST /internal/set-time   {"iso": "2026-03-23T14:00:00+01:00"}
POST /internal/reset-time  {}
GET  /internal/now         → {"now": "<iso>"}
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend import time_override
from backend.config import TIMEZONE

router = APIRouter(prefix="/internal")


class TimePayload(BaseModel):
    iso: str  # ISO 8601 datetime string, e.g. "2026-03-23T14:00:00+01:00"


@router.post("/set-time", status_code=200)
async def set_time(payload: TimePayload):
    """Override the app clock. Accepts any ISO 8601 string with timezone."""
    try:
        dt = datetime.fromisoformat(payload.iso)
    except ValueError:
        raise HTTPException(400, f"Invalid ISO datetime: {payload.iso!r}")

    if dt.tzinfo is None:
        # Assume configured timezone if no tz provided
        dt = dt.replace(tzinfo=ZoneInfo(TIMEZONE))

    time_override.set_override(dt)
    return {"now": time_override.get_now().isoformat()}


@router.post("/reset-time", status_code=200)
async def reset_time():
    """Restore the real system clock."""
    time_override.reset_override()
    return {"now": time_override.get_now().isoformat()}


@router.get("/now")
async def get_now():
    """Return the current effective time (overridden or real)."""
    return {
        "now": time_override.get_now().isoformat(),
        "overridden": time_override._override is not None,
    }
