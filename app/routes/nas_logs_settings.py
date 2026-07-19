import sqlite3

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import HTMLResponse, Response

from app import action_service, config_service, database, nas_service, notification_service, scheduler_service
from app.docker_ops import DockerOperationError
from app.web import WEBHOOK_EVENTS, redirect_to, render, safe_int

router = APIRouter()


@router.get("/nas", response_class=HTMLResponse)
def nas(request: Request):
    profiles = nas_service.list_profiles()
    return render(request, "nas.html", {
        "nas_profiles": profiles,
        "nas_status": profiles[0] if profiles else nas_service.current_status(),
        "auto_start_groups": nas_service.dependent_groups(auto_start_only=True),
        "auto_stop_groups": nas_service.dependent_groups(auto_stop_only=True),
        "recent_runs": database.list_action_runs(trigger_prefix="nas-", limit=20),
    })


@router.post("/nas/settings")
async def update_nas_settings(request: Request):
    form = await request.form()
    enabled = form.get("enabled") == "on"
    host = (form.get("host") or "").strip()
    check_interval_seconds = max(10, safe_int(form.get("check_interval_seconds"), 60))
    mount_paths_text = str(form.get("mount_paths") or "")
    if enabled and not host:
        return redirect_to("/nas", error="NAS host is required when NAS checks are enabled.")
    nas_service.update_settings(enabled, host, check_interval_seconds, mount_paths_text)
    scheduler_service.reload_nas_monitor()
    return redirect_to("/nas", message="NAS settings were saved.")


async def _save_nas_profile(request: Request, profile_id: int | None):
    form = await request.form()
    values = {
        "name": str(form.get("name") or "NAS"),
        "enabled": form.get("enabled") == "on",
        "host": str(form.get("host") or ""),
        "check_interval_seconds": max(10, safe_int(form.get("check_interval_seconds"), 60)),
        "mount_paths": str(form.get("mount_paths") or ""),
        "mac_address": str(form.get("mac_address") or ""),
        "wol_enabled": form.get("wol_enabled") == "on",
        "auto_wake": form.get("auto_wake") == "on",
        "wake_wait_seconds": max(1, safe_int(form.get("wake_wait_seconds"), 30)),
    }
    if values["enabled"] and not values["host"]:
        return redirect_to("/nas", error="Host is required for an enabled NAS profile.")
    try:
        nas_service.save_profile(profile_id, values)
    except sqlite3.IntegrityError:
        return redirect_to("/nas", error="A NAS profile with this name already exists.")
    scheduler_service.reload_nas_monitor()
    return redirect_to("/nas", message="NAS profile was saved.")


@router.post("/nas/profiles/new")
async def create_nas_profile(request: Request):
    return await _save_nas_profile(request, None)


@router.post("/nas/profiles/{profile_id}")
async def update_nas_profile(request: Request, profile_id: int):
    return await _save_nas_profile(request, profile_id)


@router.post("/nas/profiles/{profile_id}/delete")
def delete_nas_profile(profile_id: int):
    nas_service.delete_profile(profile_id)
    scheduler_service.reload_nas_monitor()
    return redirect_to("/nas", message="NAS profile was deleted.")


@router.post("/nas/profiles/{profile_id}/check")
def check_nas_profile(profile_id: int):
    status = nas_service.check_status(profile_id)
    if status["ready"]:
        return redirect_to("/nas", message=f"{status['name']} is ready.")
    return redirect_to("/nas", error=status["last_error"] or f"{status['name']} is not ready.")


@router.post("/nas/profiles/{profile_id}/wake")
def wake_nas_profile(profile_id: int):
    try:
        message = nas_service.wake(profile_id)
        return redirect_to("/nas", message=message)
    except (ValueError, OSError) as exc:
        notification_service.send_event("wol_failed", "Wake-on-LAN failed", str(exc), {"profile_id": profile_id})
        return redirect_to("/nas", error=str(exc))


@router.post("/nas/check")
def check_nas():
    status = nas_service.check_status()
    if not status["enabled"]:
        return redirect_to("/nas", message="NAS checks are disabled.")
    if status["ready"]:
        return redirect_to("/nas", message="NAS is ready.")
    return redirect_to("/nas", error=status["last_error"] or "NAS is not ready.")


@router.post("/nas/start-dependent-groups")
def start_nas_dependent_groups():
    groups = nas_service.dependent_groups(auto_start_only=True)
    if not groups:
        return redirect_to("/nas", message="No groups are marked for NAS auto-start.")
    started = 0
    errors: list[str] = []
    for group in groups:
        ready, message = nas_service.require_ready(group.get("nas_profile_id"), auto_wake=True)
        if not ready:
            errors.append(f"{group['name']}: {message}")
            continue
        try:
            action_service.start_group_run(group["id"], "start", trigger_type="nas-manual", check_nas=False)
            started += 1
        except DockerOperationError as exc:
            errors.append(f"{group['name']}: {exc}")
    if errors:
        return redirect_to("/nas", error=f"Started {started} group run(s); issues: {'; '.join(errors)}")
    return redirect_to("/nas", message=f"Started {started} NAS-dependent group run(s).")


@router.get("/logs", response_class=HTMLResponse)
def run_logs(request: Request):
    return render(request, "run_logs.html", {"runs": database.list_action_runs(limit=100)})


@router.get("/runs/{run_id}", response_class=HTMLResponse)
def action_run_detail(request: Request, run_id: int):
    run = database.get_action_run(run_id)
    if not run:
        return redirect_to("/logs", error="Run was not found.")
    return render(request, "run_detail.html", {"run": run, "steps": database.get_action_run_steps(run_id)})


@router.post("/runs/{run_id}/cancel")
def cancel_action_run(run_id: int):
    if action_service.cancel_run(run_id):
        return redirect_to(f"/runs/{run_id}", message="Cancellation requested.")
    return redirect_to(f"/runs/{run_id}", error="Run is not active or was not found.")


@router.get("/settings", response_class=HTMLResponse)
def settings(request: Request):
    return render(request, "settings.html", {
        "log_retention_days": database.get_setting("log_retention_days", "30"),
        "webhooks": notification_service.list_webhooks(),
        "webhook_events": WEBHOOK_EVENTS,
    })


@router.post("/settings/preferences")
async def update_preferences(request: Request):
    form = await request.form()
    retention = max(1, min(3650, safe_int(form.get("log_retention_days"), 30)))
    database.set_setting("log_retention_days", str(retention))
    return redirect_to("/settings", message="Settings saved.")


@router.get("/settings/export")
def export_configuration():
    content = config_service.export_configuration()
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{config_service.export_filename()}"'},
    )


@router.post("/settings/import")
async def import_configuration(file: UploadFile):
    try:
        raw = (await file.read()).decode("utf-8")
        config_service.import_configuration(raw)
        scheduler_service.reload_schedules()
        scheduler_service.reload_nas_monitor()
        return redirect_to("/settings", message="Configuration was restored.")
    except (UnicodeDecodeError, config_service.ConfigurationImportError, sqlite3.DatabaseError) as exc:
        return redirect_to("/settings", error=f"Import failed: {exc}")


@router.post("/settings/webhooks/new")
async def create_webhook(request: Request):
    form = await request.form()
    url = str(form.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return redirect_to("/settings", error="Webhook URL must use http or https.")
    notification_service.save_webhook(
        None,
        str(form.get("name") or "Webhook"),
        str(form.get("kind") or "generic"),
        url,
        form.get("enabled") == "on",
        form.getlist("events"),
    )
    return redirect_to("/settings", message="Webhook was created.")


@router.post("/settings/webhooks/{webhook_id}/delete")
def delete_webhook(webhook_id: int):
    notification_service.delete_webhook(webhook_id)
    return redirect_to("/settings", message="Webhook was deleted.")


@router.post("/settings/webhooks/{webhook_id}/test")
def test_webhook(webhook_id: int):
    try:
        notification_service.test_webhook(webhook_id)
        return redirect_to("/settings", message="Webhook test succeeded.")
    except Exception as exc:
        return redirect_to("/settings", error=str(exc))
