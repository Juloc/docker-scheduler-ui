from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app import auth, database, scheduler_service
from app.routes.dashboard import router as dashboard_router
from app.routes.groups_schedules import router as groups_schedules_router
from app.routes.nas_logs_settings import router as nas_logs_settings_router

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    auth.validate_configuration()
    database.init_db()
    scheduler_service.start_scheduler()
    yield
    scheduler_service.shutdown_scheduler()


app = FastAPI(
    title="docker-scheduler-ui",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.middleware("http")
async def same_origin_guard(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin:
            parsed = urlparse(origin)
            if parsed.netloc and parsed.netloc != request.url.netloc:
                return PlainTextResponse("Cross-origin state change rejected.", status_code=403)
    return await call_next(request)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static") or path in {"/login", "/favicon.ico"}:
        return await call_next(request)
    if auth.authenticated_user(request):
        return await call_next(request)
    return auth.auth_failed_response(request)


app.include_router(dashboard_router)
app.include_router(groups_schedules_router)
app.include_router(nas_logs_settings_router)
