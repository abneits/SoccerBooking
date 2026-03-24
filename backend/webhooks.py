import httpx
from backend.config import WEBHOOK_URL


async def fire_waitlist_promoted(
    slot_date: str,
    booking: dict,
    booked_by_username: str,
    player_username: str | None = None,
) -> None:
    """Fire waitlist_promoted webhook. Fire-and-forget, no retry."""
    if not WEBHOOK_URL:
        return
    payload = {
        "event": "waitlist_promoted",
        "slot_date": slot_date,
        "type": booking["type"],
        "user_id": booking.get("user_id"),
        "username": player_username if booking["type"] == "player" else None,
        "guest_name": booking.get("guest_name"),
        "booked_by_id": booking["booked_by_id"],
        "booked_by_username": booked_by_username,
    }
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(WEBHOOK_URL, json=payload)
    except Exception:
        pass  # fire-and-forget


async def fire_slot_not_full(slot_date: str, confirmed_count: int) -> None:
    """Fire slot_not_full webhook. Fire-and-forget, no retry."""
    if not WEBHOOK_URL:
        return
    payload = {
        "event": "slot_not_full",
        "slot_date": slot_date,
        "confirmed_count": confirmed_count,
        "spots_remaining": 10 - confirmed_count,
    }
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(WEBHOOK_URL, json=payload)
    except Exception:
        pass
