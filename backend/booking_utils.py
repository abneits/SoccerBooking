import json
from datetime import datetime
from backend import db as db_module


class BookingError(Exception):
    pass


async def get_slot_bookings(slot_id: int) -> dict:
    """Return {"confirmed": [...], "waitlist": [...]} for a slot, ordered by position."""
    rows = await db_module.fetch_all(
        "SELECT id, data FROM bookings WHERE (data->>'slot_id')::int = $1 ORDER BY (data->>'position')::int",
        slot_id,
    )
    bookings = [{"id": r["id"], **r["data"]} for r in rows]
    return {
        "confirmed": [b for b in bookings if b["status"] == "confirmed"],
        "waitlist": [b for b in bookings if b["status"] == "waitlist"],
    }


async def create_booking(
    slot_id: int,
    user_id: int | None,
    booked_by_id: int,
    booking_type: str,
    guest_name: str | None = None,
) -> dict:
    """Create a booking (confirmed or waitlist). Raises BookingError on violations."""
    if booking_type == "guest" and not guest_name:
        raise BookingError("guest_name required for guest bookings")

    pool = db_module.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Lock slot row to serialize position assignment and count checks
            await conn.fetchrow("SELECT id FROM slots WHERE id = $1 FOR UPDATE", slot_id)

            # Duplicate player booking check
            if booking_type == "player" and user_id is not None:
                existing = await conn.fetchrow(
                    "SELECT id FROM bookings WHERE (data->>'slot_id')::int = $1 "
                    "AND (data->>'user_id')::int = $2 AND data->>'type' = 'player'",
                    slot_id,
                    user_id,
                )
                if existing:
                    raise BookingError("already booked")

            confirmed_count = await conn.fetchval(
                "SELECT COUNT(*) FROM bookings WHERE (data->>'slot_id')::int = $1 AND data->>'status' = 'confirmed'",
                slot_id,
            )
            waitlist_count = await conn.fetchval(
                "SELECT COUNT(*) FROM bookings WHERE (data->>'slot_id')::int = $1 AND data->>'status' = 'waitlist'",
                slot_id,
            )

            if confirmed_count >= 10 and waitlist_count >= 2:
                raise BookingError("slot and waitlist are full")

            status = "confirmed" if confirmed_count < 10 else "waitlist"

            position = await conn.fetchval(
                "SELECT COALESCE(MAX((data->>'position')::int), 0) + 1 FROM bookings WHERE (data->>'slot_id')::int = $1",
                slot_id,
            )

            data = {
                "slot_id": slot_id,
                "user_id": user_id,
                "booked_by_id": booked_by_id,
                "type": booking_type,
                "guest_name": guest_name,
                "status": status,
                "position": position,
                "created_at": datetime.utcnow().isoformat(),
            }
            row = await conn.fetchrow(
                "INSERT INTO bookings (data) VALUES ($1::jsonb) RETURNING id, data",
                json.dumps(data),
            )
            return {"id": row["id"], **row["data"]}


async def cancel_booking(booking_id: int, slot_id: int) -> dict | None:
    """Cancel a booking and promote the lowest-position waitlist entry if a confirmed booking was cancelled.

    Returns {"promoted": {...booking dict...}} if a waitlist entry was promoted, else None.
    Caller is responsible for firing the webhook after this returns.
    """
    pool = db_module.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Lock slot to serialize promotion
            await conn.fetchrow("SELECT id FROM slots WHERE id = $1 FOR UPDATE", slot_id)

            row = await conn.fetchrow("SELECT id, data FROM bookings WHERE id = $1", booking_id)
            if not row:
                return None

            booking = dict(row["data"])
            was_confirmed = booking["status"] == "confirmed"

            await conn.execute("DELETE FROM bookings WHERE id = $1", booking_id)

            if was_confirmed:
                waitlist_row = await conn.fetchrow(
                    "SELECT id, data FROM bookings "
                    "WHERE (data->>'slot_id')::int = $1 AND data->>'status' = 'waitlist' "
                    "ORDER BY (data->>'position')::int LIMIT 1",
                    slot_id,
                )
                if waitlist_row:
                    updated = dict(waitlist_row["data"])
                    updated["status"] = "confirmed"
                    await conn.execute(
                        "UPDATE bookings SET data = $1::jsonb WHERE id = $2",
                        json.dumps(updated),
                        waitlist_row["id"],
                    )
                    return {"promoted": {"id": waitlist_row["id"], **updated}}

    return None
