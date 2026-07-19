import sqlite3

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app import action_service, database, nas_service, scheduler_service
from app.docker_ops import VALID_ACTIONS, DockerOperationError
from app.web import (
    ACTIONS,
    WEEKDAYS,
    container_map_by_name,
    enrich_groups,
    group_selection,
    missing_group_containers,
    optional_int,
    redirect_to,
    render,
    safe_int,
    schedule_rows,
    with_docker_containers,
)

router = APIRouter()


def _group_form_context(group: dict | None = None) -> dict:
    containers, docker_error = with_docker_containers()
    return {
        "group": group,
        "containers": containers,
        "docker_error": docker_error,
        "selected_containers": group_selection(group, containers),
        "missing_containers": missing_group_containers(group, containers),
        "nas_profiles": nas_service.list_profiles(),
    }


@router.get("/groups", response_class=HTMLResponse)
def groups(request: Request):
    containers, docker_error = with_docker_containers()
    return render(request, "groups.html", {
        "groups": enrich_groups(database.list_groups(), containers),
        "containers": containers,
        "docker_error": docker_error,
        "actions": ACTIONS,
        "recent_runs": database.list_action_runs(source_type="group", limit=15),
    })


@router.get("/groups/new", response_class=HTMLResponse)
def new_group(request: Request):
    return render(request, "group_form.html", _group_form_context())


@router.get("/groups/{group_id}/edit", response_class=HTMLResponse)
def edit_group(request: Request, group_id: int):
    group = database.get_group(group_id)
    if not group:
        return redirect_to("/groups", error="Group was not found.")
    return render(request, "group_form.html", _group_form_context(group))


async def _save_group_from_form(request: Request, group_id: int | None = None):
    form = await request.form()
    name = (form.get("name") or "").strip()
    delay_seconds = max(0, safe_int(form.get("delay_seconds"), 5))
    selected = form.getlist("containers")
    nas_profile_id = optional_int(form.get("nas_profile_id"))
    requires_nas = form.get("requires_nas") == "on" or nas_profile_id is not None
    auto_start = form.get("auto_start_on_nas_online") == "on"
    auto_stop = form.get("auto_stop_on_nas_offline") == "on"
    containers, _ = with_docker_containers()
    containers_by_name = container_map_by_name(containers)
    path = "/groups/new" if group_id is None else f"/groups/{group_id}/edit"
    if not name:
        return redirect_to(path, error="Name is required.")

    group_containers: list[tuple[str, str, int, int | None]] = []
    for index, container_ref in enumerate(selected, start=1):
        container = containers_by_name.get(container_ref)
        container_name = container["name"] if container else container_ref
        container_id = container["id"] if container else container_ref
        position = max(1, safe_int(form.get(f"order_{container_ref}"), index))
        delay_value = form.get(f"delay_{container_ref}")
        per_delay = None if delay_value in {None, ""} else max(0, safe_int(delay_value, delay_seconds))
        group_containers.append((container_name, container_id, position, per_delay))
    group_containers.sort(key=lambda item: item[2])

    options = {
        "nas_profile_id": nas_profile_id,
        "favorite": form.get("favorite") == "on",
        "error_policy": "continue" if form.get("error_policy") == "continue" else "stop",
        "conflict_policy": "cancel_and_start" if form.get("conflict_policy") == "cancel_and_start" else "skip",
        "wait_for_healthy": form.get("wait_for_healthy") == "on",
        "health_timeout_seconds": max(1, safe_int(form.get("health_timeout_seconds"), 60)),
    }
    try:
        if group_id is None:
            database.create_group(
                name, delay_seconds, group_containers,
                requires_nas=requires_nas,
                auto_start_on_nas_online=auto_start,
                auto_stop_on_nas_offline=auto_stop,
                **options,
            )
            return redirect_to("/groups", message="Group was created.")
        database.update_group(
            group_id, name, delay_seconds, group_containers,
            requires_nas=requires_nas,
            auto_start_on_nas_online=auto_start,
            auto_stop_on_nas_offline=auto_stop,
            **options,
        )
        return redirect_to("/groups", message="Group was updated.")
    except sqlite3.IntegrityError:
        return redirect_to(path, error="A group with this name already exists.")


@router.post("/groups/new")
async def create_group(request: Request):
    return await _save_group_from_form(request)


@router.post("/groups/{group_id}/edit")
async def update_group(request: Request, group_id: int):
    return await _save_group_from_form(request, group_id)


@router.post("/groups/{group_id}/delete")
def delete_group(group_id: int):
    database.delete_group(group_id)
    scheduler_service.reload_schedules()
    return redirect_to("/groups", message="Group was deleted.")


@router.post("/groups/{group_id}/{action}")
def group_action(group_id: int, action: str):
    if action not in VALID_ACTIONS:
        return redirect_to("/groups", error="Invalid action.")
    try:
        run_id = action_service.start_group_run(group_id, action)
        return redirect_to(f"/runs/{run_id}", message="Group action started.")
    except DockerOperationError as exc:
        return redirect_to("/groups", error=str(exc))


def _schedule_form_context(schedule: dict | None = None) -> dict:
    containers, docker_error = with_docker_containers()
    return {
        "schedule": schedule,
        "containers": containers,
        "groups": database.list_groups(),
        "nas_profiles": nas_service.list_profiles(),
        "docker_error": docker_error,
        "actions": ACTIONS,
        "weekdays": WEEKDAYS,
        "selected_weekdays": set(schedule["weekdays"].split(",")) if schedule and schedule["weekdays"] else set(),
    }


def _parse_target(value: str | None) -> tuple[str, str]:
    if not value or ":" not in value:
        raise ValueError("Target is required.")
    target_type, target_id = value.split(":", 1)
    if target_type not in {"container", "group"} or not target_id:
        raise ValueError("Invalid target.")
    return target_type, target_id


@router.get("/schedules", response_class=HTMLResponse)
def schedules(request: Request):
    containers, docker_error = with_docker_containers()
    return render(request, "schedules.html", {
        "schedules": schedule_rows(containers),
        "docker_error": docker_error,
        "recent_runs": database.list_action_runs(source_type="schedule", limit=20),
    })


@router.get("/schedules/new", response_class=HTMLResponse)
def new_schedule(request: Request):
    return render(request, "schedule_form.html", _schedule_form_context())


@router.get("/schedules/{schedule_id}/edit", response_class=HTMLResponse)
def edit_schedule(request: Request, schedule_id: int):
    schedule = database.get_schedule(schedule_id)
    if not schedule:
        return redirect_to("/schedules", error="Schedule was not found.")
    return render(request, "schedule_form.html", _schedule_form_context(schedule))


async def _save_schedule_from_form(request: Request, schedule_id: int | None = None):
    form = await request.form()
    name = (form.get("name") or "").strip()
    action = (form.get("action") or "").strip()
    time_value = (form.get("time") or "").strip()
    weekdays = ",".join(day for day, _ in WEEKDAYS if day in form.getlist("weekdays"))
    enabled = form.get("enabled") == "on"
    nas_profile_id = optional_int(form.get("nas_profile_id"))
    require_nas = form.get("require_nas") == "on" or nas_profile_id is not None
    conflict_policy = "cancel_and_start" if form.get("conflict_policy") == "cancel_and_start" else "skip"
    path = "/schedules/new" if schedule_id is None else f"/schedules/{schedule_id}/edit"
    try:
        target_type, target_id = _parse_target(form.get("target"))
        if not name:
            raise ValueError("Name is required.")
        if action not in VALID_ACTIONS:
            raise ValueError("Invalid action.")
        hour_text, minute_text = time_value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("Invalid time.")
    except (TypeError, ValueError) as exc:
        return redirect_to(path, error=str(exc))

    options = {"nas_profile_id": nas_profile_id, "conflict_policy": conflict_policy}
    if schedule_id is None:
        database.create_schedule(name, target_type, target_id, action, hour, minute, weekdays, enabled, require_nas=require_nas, **options)
        scheduler_service.reload_schedules()
        return redirect_to("/schedules", message="Schedule was created.")
    database.update_schedule(schedule_id, name, target_type, target_id, action, hour, minute, weekdays, enabled, require_nas=require_nas, **options)
    scheduler_service.reload_schedules()
    return redirect_to("/schedules", message="Schedule was updated.")


@router.post("/schedules/new")
async def create_schedule(request: Request):
    return await _save_schedule_from_form(request)


@router.post("/schedules/{schedule_id}/edit")
async def update_schedule(request: Request, schedule_id: int):
    return await _save_schedule_from_form(request, schedule_id)


@router.post("/schedules/{schedule_id}/toggle")
def toggle_schedule(schedule_id: int):
    schedule = database.get_schedule(schedule_id)
    if not schedule:
        return redirect_to("/schedules", error="Schedule was not found.")
    database.set_schedule_enabled(schedule_id, not bool(schedule["enabled"]))
    scheduler_service.reload_schedules()
    return redirect_to("/schedules", message="Schedule was updated.")


@router.post("/schedules/{schedule_id}/run")
def run_schedule_now(schedule_id: int):
    try:
        run_id = action_service.start_schedule_run(schedule_id, trigger_type="manual", background=True)
        return redirect_to(f"/runs/{run_id}", message="Schedule run started.")
    except DockerOperationError as exc:
        return redirect_to("/schedules", error=str(exc))


@router.post("/schedules/{schedule_id}/delete")
def delete_schedule(schedule_id: int):
    database.delete_schedule(schedule_id)
    scheduler_service.reload_schedules()
    return redirect_to("/schedules", message="Schedule was deleted.")
