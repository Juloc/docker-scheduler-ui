from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app import action_service, database, nas_service


scheduler = BackgroundScheduler()
NAS_MONITOR_JOB_ID = "nas-monitor"


def _job_id(schedule_id: int) -> str:
    return f"schedule-{schedule_id}"


def start_scheduler() -> None:
    reload_schedules()
    reload_nas_monitor()
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
    job = scheduler.get_job(NAS_MONITOR_JOB_ID)
    if job:
        scheduler.remove_job(NAS_MONITOR_JOB_ID)

    status = nas_service.current_status()
    if not status["enabled"]:
        return

    scheduler.add_job(
        run_nas_monitor,
        trigger="interval",
        seconds=status["check_interval_seconds"],
        id=NAS_MONITOR_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        next_run_time=datetime.now(),
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


def run_nas_monitor() -> None:
    previous_ready = database.get_setting("nas_last_automation_ready", "0") == "1"
    status = nas_service.check_status()
    if not status["enabled"]:
        return

    ready = bool(status.get("ready"))

    if ready and not previous_ready:
        _run_nas_group_actions(
            nas_service.dependent_groups(auto_start_only=True),
            "start",
            "nas-online",
        )
    elif previous_ready and not ready:
        _run_nas_group_actions(
            nas_service.dependent_groups(auto_stop_only=True),
            "stop",
            "nas-offline",
        )

    database.set_setting("nas_last_automation_ready", "1" if ready else "0")


def run_schedule(schedule_id: int) -> None:
    schedule = database.get_schedule(schedule_id)
    if not schedule or not schedule["enabled"]:
        return

    try:
        run_id = action_service.start_schedule_run(schedule_id, trigger_type="schedule", background=False)
        run = database.get_action_run(run_id)
        error = None
        if run and run["status"] in {"failed", "skipped"}:
            error = run["error"] or run["status"]
        database.mark_schedule_run(schedule_id, error)
    except Exception as exc:  # APScheduler must keep running even if one Docker action fails.
        database.mark_schedule_run(schedule_id, str(exc))


def get_next_run_time(schedule_id: int) -> str:
    job = scheduler.get_job(_job_id(schedule_id))
    if not job or not job.next_run_time:
        return "-"
    return job.next_run_time.strftime("%Y-%m-%d %H:%M")
