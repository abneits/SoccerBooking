from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from backend import db as db_module


async def get_current_user(request: Request) -> dict | None:
    """Return the logged-in user dict or None."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    row = await db_module.fetch_one("SELECT id, data FROM users WHERE id = $1", user_id)
    if not row:
        return None
    return {"id": row["id"], **row["data"]}


async def require_login(request: Request) -> dict:
    """FastAPI dependency. Redirects to /login if not authenticated."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user


async def require_admin(request: Request) -> dict:
    """FastAPI dependency. Redirects to /login or / if not admin."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    if user.get("role") != "admin":
        raise HTTPException(status_code=302, headers={"Location": "/"})
    return user
