from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app import action_service, database


scheduler = BackgroundScheduler()


def _job_id(schedule_id: int) -> str:
    return f"schedule-{schedule_id}"


def start_scheduler() -> None:
    reload_schedules()
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


def run_schedule(schedule_id: int) -> None:
    schedule = database.get_schedule(schedule_id)
    if not schedule or not schedule["enabled"]:
        return

    try:
        run_id = action_service.start_schedule_run(schedule_id, trigger_type="schedule", background=False)
        run = database.get_action_run(run_id)
        database.mark_schedule_run(schedule_id, run["error"] if run and run["status"] == "failed" else None)
    except Exception as exc:  # APScheduler must keep running even if one Docker action fails.
        database.mark_schedule_run(schedule_id, str(exc))


def get_next_run_time(schedule_id: int) -> str:
    job = scheduler.get_job(_job_id(schedule_id))
    if not job or not job.next_run_time:
        return "-"
    return job.next_run_time.strftime("%Y-%m-%d %H:%M")
