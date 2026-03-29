import json
from datetime import datetime
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from backend import db as db_module
import asyncpg

router = APIRouter()
templates = Jinja2Templates(directory="backend/templates")


@router.get("/register")
async def register_get(request: Request):
    return templates.TemplateResponse(request, "register.html")


@router.post("/register")
async def register_post(request: Request, username: str = Form(...), pin: str = Form(...)):
    error = None
    if not username.strip():
        error = "Username is required."
    elif not pin.isdigit() or len(pin) != 4:
        error = "PIN must be exactly 4 digits."
    if not error:
        data = json.dumps({
            "username": username.strip(),
            "pin": pin,
            "role": "player",
            "created_at": datetime.utcnow().isoformat(),
        })
        try:
            await db_module.execute("INSERT INTO users (data) VALUES ($1::jsonb)", data)
            return RedirectResponse("/login", status_code=303)
        except asyncpg.UniqueViolationError:
            error = "Username already taken."
    return templates.TemplateResponse(
        request, "register.html", {"error": error}, status_code=400
    )


@router.get("/login")
async def login_get(request: Request):
    return templates.TemplateResponse(request, "login.html")


@router.post("/login")
async def login_post(request: Request, username: str = Form(...), pin: str = Form(...)):
    row = await db_module.fetch_one(
        "SELECT id, data FROM users WHERE data->>'username' = $1", username
    )
    if not row or row["data"]["pin"] != pin:
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "Invalid credentials."},
            status_code=401,
        )
    request.session["user_id"] = row["id"]
    return RedirectResponse("/", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
