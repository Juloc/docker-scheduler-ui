from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from app import action_service, auth, database, nas_service
from app.docker_ops import VALID_ACTIONS, DockerOperationError, get_container_logs
from app.version import ASSET_VERSION
from app.web import agenda_rows, dashboard_stats, enrich_groups, redirect_to, render, templates, with_docker_containers

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if auth.get_auth_mode() != "form":
        return redirect_to("/")
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "request": request,
            "app_name": "docker-scheduler-ui",
            "asset_version": ASSET_VERSION,
            "next": request.query_params.get("next") or "/",
            "error": None,
        },
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request):
    form = await request.form()
    username = (form.get("username") or "").strip()
    password = form.get("password") or ""
    next_path = str(form.get("next") or "/")
    if not next_path.startswith("/") or next_path.startswith("//"):
        next_path = "/"
    if auth.verify_credentials(username, password):
        response = RedirectResponse(next_path, status_code=303)
        auth.set_session_cookie(response, username)
        return response
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "request": request,
            "app_name": "docker-scheduler-ui",
            "asset_version": ASSET_VERSION,
            "next": next_path,
            "error": "Invalid username or password.",
        },
        status_code=401,
    )


@router.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    auth.clear_session_cookie(response)
    return response


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    containers, docker_error = with_docker_containers()
    profiles = nas_service.list_profiles()
    favorite_groups = [group for group in enrich_groups(database.list_groups(), containers) if group.get("favorite")]
    agenda = agenda_rows(containers)
    return render(
        request,
        "dashboard.html",
        {
            "docker_error": docker_error,
            "stats": dashboard_stats(containers),
            "recent_runs": database.list_action_runs(limit=12),
            "favorite_groups": favorite_groups,
            "nas_profiles": profiles,
            "upcoming_schedules": agenda,
        },
    )


@router.get("/containers", response_class=HTMLResponse)
def containers_workspace(request: Request):
    containers, docker_error = with_docker_containers()
    projects = sorted({container.get("compose_project") for container in containers if container.get("compose_project")})
    return render(
        request,
        "containers.html",
        {
            "containers": containers,
            "docker_error": docker_error,
            "stats": dashboard_stats(containers),
            "compose_projects": projects,
        },
    )


@router.post("/containers/{container_id}/{action}")
def container_action(container_id: str, action: str):
    if action not in VALID_ACTIONS:
        return redirect_to("/containers", error="Invalid action.")
    try:
        run_id = action_service.start_container_run(container_id, action)
        return redirect_to(f"/runs/{run_id}", message="Action started.")
    except DockerOperationError as exc:
        return redirect_to("/containers", error=str(exc))


@router.get("/containers/{container_id}/logs", response_class=HTMLResponse)
def container_logs(request: Request, container_id: str):
    try:
        container, logs = get_container_logs(container_id, tail=100)
        return render(request, "logs.html", {"container": container, "logs": logs})
    except DockerOperationError as exc:
        return render(request, "logs.html", {"container": None, "logs": "", "docker_error": str(exc)})


@router.get("/containers/{container_id}/logs/preview", response_class=PlainTextResponse)
def container_logs_preview(container_id: str):
    try:
        _, logs = get_container_logs(container_id, tail=30)
        return PlainTextResponse(logs or "No logs available.", media_type="text/plain; charset=utf-8")
    except DockerOperationError as exc:
        return PlainTextResponse(f"Failed to load log preview: {exc}", status_code=500)
