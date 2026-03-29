import json
from fastapi import APIRouter, Request, Form, Depends
from fastapi.templating import Jinja2Templates

from backend.auth import require_login
from backend import db as db_module

router = APIRouter()
templates = Jinja2Templates(directory="backend/templates")


@router.get("/profile")
async def profile_get(request: Request, user: dict = Depends(require_login)):
    return templates.TemplateResponse(request, "profile.html", {"user": user})


@router.post("/profile/pin")
async def profile_change_pin(
    request: Request,
    current_pin: str = Form(...),
    new_pin: str = Form(...),
    confirm_pin: str = Form(...),
    user: dict = Depends(require_login),
):
    error = None
    if user["pin"] != current_pin:
        error = "Current PIN is incorrect."
    elif not new_pin.isdigit() or len(new_pin) != 4:
        error = "New PIN must be exactly 4 digits."
    elif new_pin != confirm_pin:
        error = "PINs do not match."

    if error:
        return templates.TemplateResponse(
            request, "profile.html",
            {"user": user, "error": error},
            status_code=400,
        )

    # Build updated data without the "id" key
    updated = {k: v for k, v in user.items() if k != "id"}
    updated["pin"] = new_pin
    await db_module.execute(
        "UPDATE users SET data = $1::jsonb WHERE id = $2",
        json.dumps(updated),
        user["id"],
    )
    return templates.TemplateResponse(
        request, "profile.html",
        {
            "user": {**user, "pin": new_pin},
            "success": "PIN updated successfully.",
        },
    )
