from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app import auth, database, scheduler_service
from app.docker_ops import DockerOperationError, list_containers
from app.version import APP_VERSION, ASSET_VERSION, BUILD_COMMIT

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

ACTIONS = ["start", "stop", "restart"]
WEEKDAYS = [
    ("mon", "Mon"),
    ("tue", "Tue"),
    ("wed", "Wed"),
    ("thu", "Thu"),
    ("fri", "Fri"),
    ("sat", "Sat"),
    ("sun", "Sun"),
]
WEEKDAY_LABELS = dict(WEEKDAYS)
WEBHOOK_EVENTS = [
    ("run_failed", "Run failed"),
    ("nas_online", "NAS online"),
    ("nas_offline", "NAS offline"),
    ("wol_failed", "Wake-on-LAN failed"),
]


def redirect_to(path: str, message: str | None = None, error: str | None = None) -> RedirectResponse:
    params: dict[str, str] = {}
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
        "app_version": APP_VERSION,
        "build_commit": BUILD_COMMIT,
        "asset_version": ASSET_VERSION,
        "auth_mode": auth.get_auth_mode(),
        "message": request.query_params.get("message"),
        "error": request.query_params.get("error"),
        "nav_dashboard_class": "active" if current_path == "/" else "",
        "nav_containers_class": "active" if current_path.startswith("/containers") else "",
        "nav_groups_class": "active" if current_path.startswith("/groups") else "",
        "nav_schedules_class": "active" if current_path.startswith("/schedules") else "",
        "nav_nas_class": "active" if current_path.startswith("/nas") else "",
        "nav_logs_class": "active" if current_path.startswith("/logs") or current_path.startswith("/runs") else "",
        "nav_settings_class": "active" if current_path.startswith("/settings") else "",
    }
    if context:
        base_context.update(context)
    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context=base_context,
        status_code=status_code,
    )


def safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value if value not in {None, ""} else default)
    except (TypeError, ValueError):
        return default


def optional_int(value: object) -> int | None:
    parsed = safe_int(value, 0)
    return parsed if parsed > 0 else None


def container_map(containers: list[dict]) -> dict[str, dict]:
    return {container["id"]: container for container in containers}


def container_map_by_name(containers: list[dict]) -> dict[str, dict]:
    return {container["name"]: container for container in containers}


def with_docker_containers() -> tuple[list[dict], str | None]:
    try:
        return list_containers(), None
    except DockerOperationError as exc:
        return [], str(exc)


def dashboard_stats(containers: list[dict]) -> dict:
    return {
        "total": len(containers),
        "running": sum(1 for container in containers if container["status"] == "running"),
        "stopped": sum(1 for container in containers if container["status"] in {"exited", "created", "dead"}),
        "healthy": sum(1 for container in containers if container["health"] == "healthy"),
        "unhealthy": sum(1 for container in containers if container["health"] == "unhealthy"),
        "with_ports": sum(1 for container in containers if container["ports"] != "-"),
    }


def short_id(container_id: str) -> str:
    return container_id[:12] if container_id else "-"


def enrich_groups(groups: list[dict], containers: list[dict]) -> list[dict]:
    containers_by_id = container_map(containers)
    containers_by_name = container_map_by_name(containers)
    enriched = []
    for group in groups:
        copied = dict(group)
        copied["containers"] = []
        for item in group["containers"]:
            copied_item = dict(item)
            container_name = item.get("container_name") or ""
            container = containers_by_name.get(container_name) or containers_by_id.get(item["container_id"])
            if container and not container_name:
                database.set_group_container_name(item["id"], container["name"])
                copied_item["container_name"] = container["name"]
            copied_item["display_name"] = container["name"] if container else (container_name or short_id(item["container_id"]))
            copied_item["missing"] = container is None
            copied["containers"].append(copied_item)
        enriched.append(copied)
    return enriched


def group_selection(group: dict | None, containers: list[dict]) -> dict[str, dict]:
    if not group:
        return {}
    containers_by_id = container_map(containers)
    selected: dict[str, dict] = {}
    for item in group["containers"]:
        container_name = item.get("container_name")
        ref = container_name
        if not ref:
            container = containers_by_id.get(item["container_id"])
            ref = container["name"] if container else item["container_id"]
        selected[ref] = {"position": item["position"], "delay_seconds": item.get("delay_seconds")}
    return selected


def missing_group_containers(group: dict | None, containers: list[dict]) -> list[dict]:
    if not group:
        return []
    current_ids = {container["id"] for container in containers}
    current_names = {container["name"] for container in containers}
    missing = []
    for item in group["containers"]:
        container_name = item.get("container_name") or ""
        if item["container_id"] not in current_ids and container_name not in current_names:
            ref = container_name or item["container_id"]
            missing.append({
                "ref": ref,
                "position": item["position"],
                "delay_seconds": item.get("delay_seconds"),
                "name": container_name or short_id(item["container_id"]),
            })
    return missing


def weekday_label(weekdays: str) -> str:
    if not weekdays:
        return "Daily"
    return ", ".join(WEEKDAY_LABELS.get(day, day) for day in weekdays.split(",") if day)


def schedule_target_label(schedule: dict, containers_by_id: dict[str, dict], groups_by_id: dict[int, dict]) -> str:
    if schedule["target_type"] == "container":
        containers_by_name = {container["name"]: container for container in containers_by_id.values()}
        container = containers_by_name.get(schedule["target_id"]) or containers_by_id.get(schedule["target_id"])
        return container["name"] if container else f"Container {schedule['target_id']}"
    group = groups_by_id.get(safe_int(schedule["target_id"]))
    return group["name"] if group else f"Group {schedule['target_id']}"


def schedule_rows(containers: list[dict] | None = None) -> list[dict]:
    containers = containers if containers is not None else with_docker_containers()[0]
    groups_list = database.list_groups()
    containers_by_id = container_map(containers)
    groups_by_id = {group["id"]: group for group in groups_list}
    rows = []
    for schedule in database.list_schedules():
        copied = dict(schedule)
        copied["target_label"] = schedule_target_label(schedule, containers_by_id, groups_by_id)
        copied["weekdays_label"] = weekday_label(schedule["weekdays"])
        copied["time_label"] = f"{schedule['hour']:02d}:{schedule['minute']:02d}"
        copied["next_run"] = scheduler_service.get_next_run_time(schedule["id"])
        rows.append(copied)
    return rows


def agenda_rows(containers: list[dict]) -> list[dict]:
    schedules = {row["id"]: row for row in schedule_rows(containers)}
    rows = []
    for occurrence in scheduler_service.get_upcoming_occurrences(days=7):
        schedule = schedules.get(occurrence["schedule_id"], {})
        rows.append({
            **occurrence,
            "target_label": schedule.get("target_label", occurrence["target_id"]),
            "run_at_label": occurrence["run_at"].strftime("%Y-%m-%d %H:%M"),
        })
    return rows
