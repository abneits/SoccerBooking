import json
from datetime import datetime, date as date_type
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.auth import require_admin
from backend.config import TIMEZONE
from backend.slot_utils import compute_slot_state, SlotState
from backend.booking_utils import create_booking, cancel_booking, get_slot_bookings, BookingError
from backend.webhooks import fire_waitlist_promoted
from backend import db as db_module

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="backend/templates")


def _now() -> datetime:
    return datetime.now(ZoneInfo(TIMEZONE))


@router.get("")
async def admin_index(request: Request, user: dict = Depends(require_admin)):
    now = _now()
    slots = await db_module.fetch_all(
        "SELECT id, data FROM slots ORDER BY data->>'date' DESC LIMIT 10"
    )
    slot_list = [{"id": r["id"], **r["data"]} for r in slots]

    users = await db_module.fetch_all("SELECT id, data FROM users ORDER BY id")
    user_list = [{"id": r["id"], **r["data"]} for r in users]

    # Find the most recent non-future slot or the upcoming one for booking management
    current_slot = slot_list[0] if slot_list else None
    current_bookings = None
    current_state = None
    if current_slot:
        current_state = compute_slot_state(current_slot, now)
        raw_bookings = await get_slot_bookings(current_slot["id"])
        # Enrich with usernames
        all_b = raw_bookings["confirmed"] + raw_bookings["waitlist"]
        by_ids = list({b["booked_by_id"] for b in all_b if b.get("booked_by_id")})
        umap = {}
        for uid in by_ids:
            row = await db_module.fetch_one("SELECT data FROM users WHERE id = $1", uid)
            if row:
                umap[uid] = row["data"]["username"]
        def enrich(b):
            return {**b, "booked_by_username": umap.get(b.get("booked_by_id"), "?")}
        current_bookings = {
            "confirmed": [enrich(b) for b in raw_bookings["confirmed"]],
            "waitlist": [enrich(b) for b in raw_bookings["waitlist"]],
        }

    return templates.TemplateResponse("admin/index.html", {
        "request": request,
        "user": user,
        "slots": slot_list,
        "current_slot": current_slot,
        "current_bookings": current_bookings,
        "current_state": current_state,
        "users": user_list,
        "now": now,
    })


@router.post("/slot/cancel")
async def admin_cancel_slot(
    request: Request,
    user: dict = Depends(require_admin),
    slot_id: int = Form(None),
    date: str = Form(None),
    reason: str = Form(""),
):
    if slot_id:
        row = await db_module.fetch_one("SELECT id, data FROM slots WHERE id = $1", slot_id)
        if not row:
            raise HTTPException(404)
        updated = {**row["data"], "status": "cancelled", "cancelled_reason": reason}
        await db_module.execute(
            "UPDATE slots SET data = $1::jsonb WHERE id = $2",
            json.dumps(updated), slot_id
        )
    elif date:
        existing = await db_module.fetch_one(
            "SELECT id, data FROM slots WHERE data->>'date' = $1", date
        )
        if existing:
            updated = {**existing["data"], "status": "cancelled", "cancelled_reason": reason}
            await db_module.execute(
                "UPDATE slots SET data = $1::jsonb WHERE id = $2",
                json.dumps(updated), existing["id"]
            )
        else:
            data = json.dumps({
                "date": date,
                "status": "cancelled",
                "cancelled_reason": reason,
                "nudge_sent": False,
                "details": {},
            })
            await db_module.execute("INSERT INTO slots (data) VALUES ($1::jsonb)", data)
    return RedirectResponse("/admin", status_code=303)


@router.post("/booking/cancel")
async def admin_cancel_booking(
    request: Request,
    booking_id: int = Form(...),
    slot_id: int = Form(...),
    user: dict = Depends(require_admin),
):
    now = _now()
    slot_row = await db_module.fetch_one("SELECT id, data FROM slots WHERE id = $1", slot_id)
    if not slot_row:
        raise HTTPException(404)
    slot = {"id": slot_row["id"], **slot_row["data"]}
    state = compute_slot_state(slot, now)

    if state not in (SlotState.OPEN, SlotState.CLOSED):
        raise HTTPException(403, "Cannot modify bookings during FROZEN or CANCELLED state")

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

    return RedirectResponse("/admin", status_code=303)


@router.post("/booking/add")
async def admin_add_booking(
    request: Request,
    slot_id: int = Form(...),
    username: str = Form(...),
    user: dict = Depends(require_admin),
):
    now = _now()
    slot_row = await db_module.fetch_one("SELECT id, data FROM slots WHERE id = $1", slot_id)
    if not slot_row:
        raise HTTPException(404)
    slot = {"id": slot_row["id"], **slot_row["data"]}
    state = compute_slot_state(slot, now)

    if state not in (SlotState.OPEN, SlotState.CLOSED):
        raise HTTPException(403, "Cannot add bookings during FROZEN or CANCELLED state")

    player_row = await db_module.fetch_one(
        "SELECT id, data FROM users WHERE data->>'username' = $1", username
    )
    if not player_row:
        raise HTTPException(404, f"User '{username}' not found")

    try:
        await create_booking(slot_id, player_row["id"], user["id"], "player")
    except BookingError as e:
        raise HTTPException(400, str(e))

    return RedirectResponse("/admin", status_code=303)


@router.post("/user/reset-pin")
async def admin_reset_pin(
    request: Request,
    user_id: int = Form(...),
    new_pin: str = Form(...),
    user: dict = Depends(require_admin),
):
    if not new_pin.isdigit() or len(new_pin) != 4:
        raise HTTPException(400, "PIN must be exactly 4 digits")
    row = await db_module.fetch_one("SELECT data FROM users WHERE id = $1", user_id)
    if not row:
        raise HTTPException(404)
    updated = {**row["data"], "pin": new_pin}
    await db_module.execute(
        "UPDATE users SET data = $1::jsonb WHERE id = $2",
        json.dumps(updated), user_id
    )
    return RedirectResponse("/admin", status_code=303)


@router.post("/user/delete")
async def admin_delete_user(
    request: Request,
    user_id: int = Form(...),
    user: dict = Depends(require_admin),
):
    # Cascade-delete bookings on open slots, with waitlist promotion
    open_slots = await db_module.fetch_all(
        "SELECT id, data FROM slots WHERE data->>'status' = 'open'"
    )
    for slot_row in open_slots:
        slot_id = slot_row["id"]
        slot_data = {"id": slot_id, **slot_row["data"]}
        bookings = await db_module.fetch_all(
            "SELECT id, data FROM bookings "
            "WHERE (data->>'slot_id')::int = $1 "
            "AND ((data->>'user_id')::int = $2 OR (data->>'booked_by_id')::int = $2)",
            slot_id, user_id
        )
        for b_row in bookings:
            b = {"id": b_row["id"], **b_row["data"]}
            result = await cancel_booking(b["id"], slot_id)
            if result and result.get("promoted"):
                promoted = result["promoted"]
                by_row = await db_module.fetch_one(
                    "SELECT data FROM users WHERE id = $1", promoted["booked_by_id"]
                )
                booked_by_username = by_row["data"]["username"] if by_row else ""
                player_username = None
                if promoted["type"] == "player" and promoted.get("user_id"):
                    p_row = await db_module.fetch_one(
                        "SELECT data FROM users WHERE id = $1", promoted["user_id"]
                    )
                    player_username = p_row["data"]["username"] if p_row else None
                await fire_waitlist_promoted(slot_data["date"], promoted, booked_by_username, player_username)

    await db_module.execute("DELETE FROM users WHERE id = $1", user_id)
    return RedirectResponse("/admin", status_code=303)


@router.post("/user/set-role")
async def admin_set_role(
    request: Request,
    user_id: int = Form(...),
    role: str = Form(...),
    user: dict = Depends(require_admin),
):
    if role not in ("player", "admin"):
        raise HTTPException(400, "Role must be 'player' or 'admin'")
    row = await db_module.fetch_one("SELECT data FROM users WHERE id = $1", user_id)
    if not row:
        raise HTTPException(404)
    updated = {**row["data"], "role": role}
    await db_module.execute(
        "UPDATE users SET data = $1::jsonb WHERE id = $2",
        json.dumps(updated), user_id
    )
    return RedirectResponse("/admin", status_code=303)
