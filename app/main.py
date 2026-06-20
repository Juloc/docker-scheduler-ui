import sqlite3
from contextlib import asynccontextmanager
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app import database, scheduler_service
from app.auth import require_auth
from app.docker_ops import (
    VALID_ACTIONS,
    DockerOperationError,
    get_container_logs,
    list_containers,
    run_container_action,
    run_group_action,
)


BASE_DIR = Path(__file__).resolve().parent
ACTIONS = ["start", "stop", "restart"]
WEEKDAYS = [
    ("mon", "Mo"),
    ("tue", "Di"),
    ("wed", "Mi"),
    ("thu", "Do"),
    ("fri", "Fr"),
    ("sat", "Sa"),
    ("sun", "So"),
]
WEEKDAY_LABELS = dict(WEEKDAYS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.init_db()
    scheduler_service.start_scheduler()
    yield
    scheduler_service.shutdown_scheduler()


app = FastAPI(
    title="docker-scheduler-ui",
    dependencies=[Depends(require_auth)],
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def redirect_to(path: str, message: str | None = None, error: str | None = None) -> RedirectResponse:
    params = {}
    if message:
        params["message"] = message
    if error:
        params["error"] = error
    suffix = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(f"{path}{suffix}", status_code=303)


def render(request: Request, template_name: str, context: dict | None = None, status_code: int = 200):
    current_path = request.url.path
    base_context = {
        "request": request,
        "app_name": "docker-scheduler-ui",
        "message": request.query_params.get("message"),
        "error": request.query_params.get("error"),
        "nav_dashboard_class": "active" if current_path == "/" else "",
        "nav_groups_class": "active" if current_path.startswith("/groups") else "",
        "nav_schedules_class": "active" if current_path.startswith("/schedules") else "",
    }
    if context:
        base_context.update(context)
    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context=base_context,
        status_code=status_code,
    )


def _safe_int(value: str | None, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _container_map(containers: list[dict]) -> dict[str, dict]:
    return {container["id"]: container for container in containers}


def _with_docker_containers() -> tuple[list[dict], str | None]:
    try:
        return list_containers(), None
    except DockerOperationError as exc:
        return [], str(exc)


def _short_id(container_id: str) -> str:
    return container_id[:12] if container_id else "-"


def _enrich_groups(groups: list[dict], containers: list[dict]) -> list[dict]:
    containers_by_id = _container_map(containers)
    enriched = []
    for group in groups:
        copied = dict(group)
        copied["containers"] = []
        for item in group["containers"]:
            copied_item = dict(item)
            container = containers_by_id.get(item["container_id"])
            copied_item["display_name"] = container["name"] if container else _short_id(item["container_id"])
            copied_item["missing"] = container is None
            copied["containers"].append(copied_item)
        enriched.append(copied)
    return enriched


def _group_selection(group: dict | None) -> dict[str, int]:
    if not group:
        return {}
    return {item["container_id"]: item["position"] for item in group["containers"]}


def _missing_group_containers(group: dict | None, containers: list[dict]) -> list[dict]:
    if not group:
        return []

    current_ids = {container["id"] for container in containers}
    missing = []
    for item in group["containers"]:
        if item["container_id"] not in current_ids:
            missing.append(
                {
                    "id": item["container_id"],
                    "position": item["position"],
                    "name": _short_id(item["container_id"]),
                }
            )
    return missing


def _weekday_label(weekdays: str) -> str:
    if not weekdays:
        return "Taeglich"
    return ", ".join(WEEKDAY_LABELS.get(day, day) for day in weekdays.split(",") if day)


def _schedule_target_label(schedule: dict, containers_by_id: dict[str, dict], groups_by_id: dict[int, dict]) -> str:
    if schedule["target_type"] == "container":
        container = containers_by_id.get(schedule["target_id"])
        return container["name"] if container else f"Container {_short_id(schedule['target_id'])}"
    group = groups_by_id.get(_safe_int(schedule["target_id"]))
    return group["name"] if group else f"Gruppe {schedule['target_id']}"


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    containers, docker_error = _with_docker_containers()
    return render(request, "dashboard.html", {"containers": containers, "docker_error": docker_error})


@app.post("/containers/{container_id}/{action}")
def container_action(container_id: str, action: str):
    if action not in VALID_ACTIONS:
        return redirect_to("/", error="Ungueltige Aktion.")
    try:
        message = run_container_action(container_id, action)
        return redirect_to("/", message=message)
    except DockerOperationError as exc:
        return redirect_to("/", error=str(exc))


@app.get("/containers/{container_id}/logs", response_class=HTMLResponse)
def container_logs(request: Request, container_id: str):
    try:
        container, logs = get_container_logs(container_id, tail=100)
        return render(request, "logs.html", {"container": container, "logs": logs})
    except DockerOperationError as exc:
        return render(request, "logs.html", {"container": None, "logs": "", "docker_error": str(exc)})


@app.get("/groups", response_class=HTMLResponse)
def groups(request: Request):
    containers, docker_error = _with_docker_containers()
    group_rows = _enrich_groups(database.list_groups(), containers)
    return render(
        request,
        "groups.html",
        {"groups": group_rows, "containers": containers, "docker_error": docker_error, "actions": ACTIONS},
    )


@app.get("/groups/new", response_class=HTMLResponse)
def new_group(request: Request):
    containers, docker_error = _with_docker_containers()
    return render(
        request,
        "group_form.html",
        {
            "group": None,
            "containers": containers,
            "docker_error": docker_error,
            "selected_containers": {},
            "missing_containers": [],
        },
    )


@app.get("/groups/{group_id}/edit", response_class=HTMLResponse)
def edit_group(request: Request, group_id: int):
    group = database.get_group(group_id)
    if not group:
        return redirect_to("/groups", error="Gruppe wurde nicht gefunden.")
    containers, docker_error = _with_docker_containers()
    return render(
        request,
        "group_form.html",
        {
            "group": group,
            "containers": containers,
            "docker_error": docker_error,
            "selected_containers": _group_selection(group),
            "missing_containers": _missing_group_containers(group, containers),
        },
    )


async def _save_group_from_form(request: Request, group_id: int | None = None):
    form = await request.form()
    name = (form.get("name") or "").strip()
    delay_seconds = max(0, _safe_int(form.get("delay_seconds"), 5))
    selected = form.getlist("containers")

    if not name:
        return redirect_to("/groups/new" if group_id is None else f"/groups/{group_id}/edit", error="Name fehlt.")

    group_containers: list[tuple[str, int]] = []
    for index, container_id in enumerate(selected, start=1):
        position = max(1, _safe_int(form.get(f"order_{container_id}"), index))
        group_containers.append((container_id, position))
    group_containers.sort(key=lambda item: item[1])

    try:
        if group_id is None:
            database.create_group(name, delay_seconds, group_containers)
            return redirect_to("/groups", message="Gruppe wurde erstellt.")
        database.update_group(group_id, name, delay_seconds, group_containers)
        return redirect_to("/groups", message="Gruppe wurde aktualisiert.")
    except sqlite3.IntegrityError:
        return redirect_to(
            "/groups/new" if group_id is None else f"/groups/{group_id}/edit",
            error="Eine Gruppe mit diesem Namen existiert bereits.",
        )


@app.post("/groups/new")
async def create_group(request: Request):
    return await _save_group_from_form(request)


@app.post("/groups/{group_id}/edit")
async def update_group(request: Request, group_id: int):
    return await _save_group_from_form(request, group_id)


@app.post("/groups/{group_id}/delete")
def delete_group(group_id: int):
    database.delete_group(group_id)
    scheduler_service.reload_schedules()
    return redirect_to("/groups", message="Gruppe wurde geloescht.")


@app.post("/groups/{group_id}/{action}")
def group_action(group_id: int, action: str):
    if action not in VALID_ACTIONS:
        return redirect_to("/groups", error="Ungueltige Aktion.")
    try:
        message = run_group_action(group_id, action)
        return redirect_to("/groups", message=message)
    except DockerOperationError as exc:
        return redirect_to("/groups", error=str(exc))


@app.get("/schedules", response_class=HTMLResponse)
def schedules(request: Request):
    containers, docker_error = _with_docker_containers()
    groups_list = database.list_groups()
    containers_by_id = _container_map(containers)
    groups_by_id = {group["id"]: group for group in groups_list}
    schedule_rows = []
    for schedule in database.list_schedules():
        copied = dict(schedule)
        copied["target_label"] = _schedule_target_label(schedule, containers_by_id, groups_by_id)
        copied["weekdays_label"] = _weekday_label(schedule["weekdays"])
        copied["time_label"] = f"{schedule['hour']:02d}:{schedule['minute']:02d}"
        copied["next_run"] = scheduler_service.get_next_run_time(schedule["id"])
        schedule_rows.append(copied)
    return render(
        request,
        "schedules.html",
        {"schedules": schedule_rows, "docker_error": docker_error},
    )


@app.get("/schedules/new", response_class=HTMLResponse)
def new_schedule(request: Request):
    containers, docker_error = _with_docker_containers()
    return render(
        request,
        "schedule_form.html",
        {
            "schedule": None,
            "containers": containers,
            "groups": database.list_groups(),
            "docker_error": docker_error,
            "actions": ACTIONS,
            "weekdays": WEEKDAYS,
            "selected_weekdays": set(),
        },
    )


@app.get("/schedules/{schedule_id}/edit", response_class=HTMLResponse)
def edit_schedule(request: Request, schedule_id: int):
    schedule = database.get_schedule(schedule_id)
    if not schedule:
        return redirect_to("/schedules", error="Zeitplan wurde nicht gefunden.")
    containers, docker_error = _with_docker_containers()
    return render(
        request,
        "schedule_form.html",
        {
            "schedule": schedule,
            "containers": containers,
            "groups": database.list_groups(),
            "docker_error": docker_error,
            "actions": ACTIONS,
            "weekdays": WEEKDAYS,
            "selected_weekdays": set(schedule["weekdays"].split(",")) if schedule["weekdays"] else set(),
        },
    )


def _parse_target(value: str | None) -> tuple[str, str]:
    if not value or ":" not in value:
        raise ValueError("Ziel fehlt.")
    target_type, target_id = value.split(":", 1)
    if target_type not in {"container", "group"} or not target_id:
        raise ValueError("Ungueltiges Ziel.")
    return target_type, target_id


async def _save_schedule_from_form(request: Request, schedule_id: int | None = None):
    form = await request.form()
    name = (form.get("name") or "").strip()
    action = (form.get("action") or "").strip()
    time_value = (form.get("time") or "").strip()
    weekdays = ",".join(day for day, _ in WEEKDAYS if day in form.getlist("weekdays"))
    enabled = form.get("enabled") == "on"
    path = "/schedules/new" if schedule_id is None else f"/schedules/{schedule_id}/edit"

    try:
        target_type, target_id = _parse_target(form.get("target"))
        if not name:
            raise ValueError("Name fehlt.")
        if action not in VALID_ACTIONS:
            raise ValueError("Ungueltige Aktion.")
        hour_text, minute_text = time_value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("Ungueltige Uhrzeit.")
    except (TypeError, ValueError) as exc:
        return redirect_to(path, error=str(exc))

    if schedule_id is None:
        database.create_schedule(name, target_type, target_id, action, hour, minute, weekdays, enabled)
        scheduler_service.reload_schedules()
        return redirect_to("/schedules", message="Zeitplan wurde erstellt.")

    database.update_schedule(schedule_id, name, target_type, target_id, action, hour, minute, weekdays, enabled)
    scheduler_service.reload_schedules()
    return redirect_to("/schedules", message="Zeitplan wurde aktualisiert.")


@app.post("/schedules/new")
async def create_schedule(request: Request):
    return await _save_schedule_from_form(request)


@app.post("/schedules/{schedule_id}/edit")
async def update_schedule(request: Request, schedule_id: int):
    return await _save_schedule_from_form(request, schedule_id)


@app.post("/schedules/{schedule_id}/toggle")
def toggle_schedule(schedule_id: int):
    schedule = database.get_schedule(schedule_id)
    if not schedule:
        return redirect_to("/schedules", error="Zeitplan wurde nicht gefunden.")
    database.set_schedule_enabled(schedule_id, not bool(schedule["enabled"]))
    scheduler_service.reload_schedules()
    return redirect_to("/schedules", message="Zeitplan wurde aktualisiert.")


@app.post("/schedules/{schedule_id}/delete")
def delete_schedule(schedule_id: int):
    database.delete_schedule(schedule_id)
    scheduler_service.reload_schedules()
    return redirect_to("/schedules", message="Zeitplan wurde geloescht.")
