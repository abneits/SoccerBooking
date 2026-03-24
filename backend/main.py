from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from backend.config import DATABASE_URL, SECRET_KEY, SESSION_MAX_AGE
from backend import db as db_module
from backend.routers import auth as auth_router
from backend.routers import main as main_router
from backend.routers import admin as admin_router
from backend.routers import profile as profile_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db_module.init_pool(DATABASE_URL)
    from backend.scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    yield
    stop_scheduler()
    await db_module.close_pool()


app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=SESSION_MAX_AGE)
app.mount("/static", StaticFiles(directory="backend/static"), name="static")

app.include_router(auth_router.router)
app.include_router(main_router.router)
app.include_router(admin_router.router)
app.include_router(profile_router.router)
