from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.templating import Jinja2Templates

from backend.auth import require_login
from backend.config import TIMEZONE
from backend.slot_utils import get_or_create_upcoming_slot, compute_slot_state, SlotState
from backend.booking_utils import create_booking, cancel_booking, get_slot_bookings, BookingError
from backend.webhooks import fire_waitlist_promoted
from backend import db as db_module

router = APIRouter()
templates = Jinja2Templates(directory="backend/templates")


def _now() -> datetime:
    return datetime.now(ZoneInfo(TIMEZONE))


@router.get("/")
async def index(request: Request, user: dict = Depends(require_login)):
    now = _now()
    slot = await get_or_create_upcoming_slot(now)
    context = {"user": user, "slot": None, "bookings": None, "state": None}
    if slot:
        state = compute_slot_state(slot, now)
        slot_bookings = await get_slot_bookings(slot["id"])
        bookings = await _enrich_bookings(slot_bookings)
        context.update({"slot": slot, "state": state, "bookings": bookings})
    return templates.TemplateResponse(request, "index.html", context)


@router.post("/book")
async def book(
    request: Request,
    slot_id: int = Form(...),
    booking_type: str = Form(alias="type"),
    guest_name: str = Form(None),
    user: dict = Depends(require_login),
):
    now = _now()
    slot_row = await db_module.fetch_one("SELECT id, data FROM slots WHERE id = $1", slot_id)
    if not slot_row:
        raise HTTPException(404)
    slot = {"id": slot_row["id"], **slot_row["data"]}
    state = compute_slot_state(slot, now)

    if state == SlotState.CANCELLED:
        raise HTTPException(403, "Slot is cancelled")
    if state not in (SlotState.OPEN,):
        raise HTTPException(403, "Booking not allowed in current slot state")

    user_id = user["id"] if booking_type == "player" else None
    try:
        await create_booking(slot_id, user_id, user["id"], booking_type, guest_name)
    except BookingError as e:
        raise HTTPException(400, str(e))

    slot_bookings = await get_slot_bookings(slot_id)
    enriched = await _enrich_bookings(slot_bookings)
    return templates.TemplateResponse(
        request, "partials/slot_panel.html",
        {"user": user, "slot": slot, "state": state, "bookings": enriched},
    )


@router.post("/cancel")
async def cancel(
    request: Request,
    booking_id: int = Form(...),
    slot_id: int = Form(...),
    user: dict = Depends(require_login),
):
    now = _now()
    slot_row = await db_module.fetch_one("SELECT id, data FROM slots WHERE id = $1", slot_id)
    if not slot_row:
        raise HTTPException(404)
    slot = {"id": slot_row["id"], **slot_row["data"]}
    state = compute_slot_state(slot, now)

    # Players can only cancel during OPEN; admins use /admin for CLOSED
    if state not in (SlotState.OPEN,):
        raise HTTPException(403, "Cancellation not allowed in current slot state")

    booking_row = await db_module.fetch_one("SELECT id, data FROM bookings WHERE id = $1", booking_id)
    if not booking_row:
        raise HTTPException(404)

    booking = booking_row["data"]
    # Only booked_by_id can cancel (admins use /admin)
    if booking["booked_by_id"] != user["id"]:
        raise HTTPException(403, "You can only cancel your own bookings")

    result = await cancel_booking(booking_id, slot_id)
    if result and result.get("promoted"):
        promoted = result["promoted"]
        by_row = await db_module.fetch_one("SELECT data FROM users WHERE id = $1", promoted["booked_by_id"])
        booked_by_username = by_row["data"]["username"] if by_row else ""
        player_username = None
        if promoted["type"] == "player" and promoted.get("user_id"):
            p_row = await db_module.fetch_one("SELECT data FROM users WHERE id = $1", promoted["user_id"])
            player_username = p_row["data"]["username"] if p_row else None
        await fire_waitlist_promoted(slot["date"], promoted, booked_by_username, player_username)

    slot_bookings = await get_slot_bookings(slot_id)
    enriched = await _enrich_bookings(slot_bookings)
    return templates.TemplateResponse(
        request, "partials/slot_panel.html",
        {"user": user, "slot": slot, "state": state, "bookings": enriched},
    )


async def _enrich_bookings(slot_bookings: dict) -> dict:
    """Resolve booked_by_username for display."""
    all_bookings = slot_bookings["confirmed"] + slot_bookings["waitlist"]
    user_ids = list({b["booked_by_id"] for b in all_bookings if b.get("booked_by_id")})
    users = {}
    for uid in user_ids:
        row = await db_module.fetch_one("SELECT id, data FROM users WHERE id = $1", uid)
        if row:
            users[uid] = row["data"]["username"]

    def enrich(b):
        return {**b, "booked_by_username": users.get(b.get("booked_by_id"), "?")}

    return {
        "confirmed": [enrich(b) for b in slot_bookings["confirmed"]],
        "waitlist": [enrich(b) for b in slot_bookings["waitlist"]],
    }
