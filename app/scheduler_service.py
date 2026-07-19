from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app import action_service, database, nas_service


scheduler = BackgroundScheduler()
NAS_MONITOR_PREFIX = "nas-monitor-"
LEGACY_NAS_MONITOR_JOB_ID = "nas-monitor-legacy"
RETENTION_JOB_ID = "log-retention"


def _job_id(schedule_id: int) -> str:
    return f"schedule-{schedule_id}"


def start_scheduler() -> None:
    reload_schedules()
    reload_nas_monitor()
    _reload_retention_job()
    if not scheduler.running:
        scheduler.start()


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def reload_schedules() -> None:
    for job in scheduler.get_jobs():
        if job.id.startswith("schedule-"):
            scheduler.remove_job(job.id)
    for schedule in database.list_enabled_schedules():
        trigger = CronTrigger(
            day_of_week=schedule["weekdays"] or None,
            hour=schedule["hour"],
            minute=schedule["minute"],
        )
        scheduler.add_job(
            run_schedule,
            trigger=trigger,
            args=[schedule["id"]],
            id=_job_id(schedule["id"]),
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=300,
        )


def reload_nas_monitor() -> None:
    """Reload all NAS monitor jobs; kept singular for backwards compatibility."""
    for job in scheduler.get_jobs():
        if job.id.startswith(NAS_MONITOR_PREFIX):
            scheduler.remove_job(job.id)

    profiles = nas_service.list_profiles()
    if profiles:
        for profile in profiles:
            if not profile["enabled"]:
                continue
            scheduler.add_job(
                run_nas_monitor,
                trigger="interval",
                seconds=profile["check_interval_seconds"],
                args=[profile["id"]],
                id=f"{NAS_MONITOR_PREFIX}{profile['id']}",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                next_run_time=datetime.now(),
            )
        return

    status = nas_service.current_status()
    if status["enabled"]:
        scheduler.add_job(
            run_nas_monitor,
            trigger="interval",
            seconds=status["check_interval_seconds"],
            args=[None],
            id=LEGACY_NAS_MONITOR_JOB_ID,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            next_run_time=datetime.now(),
        )


def _reload_retention_job() -> None:
    existing = scheduler.get_job(RETENTION_JOB_ID)
    if existing:
        scheduler.remove_job(RETENTION_JOB_ID)
    scheduler.add_job(
        database.compact_old_action_runs,
        trigger="interval",
        hours=24,
        id=RETENTION_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )


def _run_nas_group_actions(groups: list[dict], action: str, trigger_type: str) -> None:
    for group in groups:
        try:
            action_service.start_group_run(
                group["id"],
                action,
                background=False,
                trigger_type=trigger_type,
                check_nas=False,
            )
        except Exception:
            continue


def run_nas_monitor(profile_id: int | None = None) -> None:
    status_before = nas_service.current_status(profile_id)
    if not status_before["enabled"]:
        return

    if profile_id:
        profile = database.get_nas_profile(profile_id)
        previous_ready = bool(profile and profile.get("last_automation_ready"))
    else:
        previous_ready = database.get_setting("nas_last_automation_ready", "0") == "1"

    status = nas_service.check_status(profile_id)
    ready = bool(status.get("ready"))

    if ready and not previous_ready:
        _run_nas_group_actions(
            nas_service.dependent_groups(auto_start_only=True, profile_id=profile_id),
            "start",
            "nas-online",
        )
    elif previous_ready and not ready:
        _run_nas_group_actions(
            nas_service.dependent_groups(auto_stop_only=True, profile_id=profile_id),
            "stop",
            "nas-offline",
        )

    if profile_id:
        database.update_nas_profile_status(profile_id, last_automation_ready=ready)
    else:
        database.set_setting("nas_last_automation_ready", "1" if ready else "0")


def run_schedule(schedule_id: int) -> None:
    schedule = database.get_schedule(schedule_id)
    if not schedule or not schedule["enabled"]:
        return
    try:
        run_id = action_service.start_schedule_run(schedule_id, trigger_type="schedule", background=False)
        run = database.get_action_run(run_id)
        error = None
        if run and run["status"] in {"failed", "skipped", "cancelled"}:
            error = run["error"] or run["status"]
        database.mark_schedule_run(schedule_id, error)
    except Exception as exc:
        database.mark_schedule_run(schedule_id, str(exc))


def get_next_run_time(schedule_id: int) -> str:
    job = scheduler.get_job(_job_id(schedule_id))
    if not job or not job.next_run_time:
        return "-"
    return job.next_run_time.strftime("%Y-%m-%d %H:%M")
