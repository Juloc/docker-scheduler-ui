import threading
import time
from typing import Callable

from app import database
from app.docker_ops import DockerOperationError, run_container_action


def _run_async(target: Callable[[], None]) -> None:
    thread = threading.Thread(target=target, daemon=True)
    thread.start()


def _finish_run_failed(run_id: int, exc: Exception) -> None:
    database.finish_action_run(run_id, "failed", str(exc))


def _container_ref(item: dict) -> str:
    return item.get("container_name") or item.get("container_id") or ""


def _execute_container_step(run_id: int, position: int, container_ref: str, action: str) -> None:
    step_id = database.create_action_step(run_id, position, "container", container_ref, action)
    try:
        message = run_container_action(container_ref, action)
        database.finish_action_step(step_id, "success", message)
    except Exception as exc:
        database.finish_action_step(step_id, "failed", str(exc))
        raise


def _execute_group_steps(run_id: int, group: dict, action: str) -> None:
    containers = group.get("containers", [])
    if not containers:
        raise DockerOperationError("Group contains no containers.")

    delay_seconds = max(0, int(group.get("delay_seconds") or 0))
    for index, item in enumerate(containers, start=1):
        ref = _container_ref(item)
        if not ref:
            raise DockerOperationError("Group contains a container without name or id.")
        _execute_container_step(run_id, index, ref, action)
        if delay_seconds and index < len(containers):
            time.sleep(delay_seconds)


def start_container_run(container_ref: str, action: str, background: bool = True) -> int:
    run_id = database.create_action_run(
        source_type="container",
        source_id=container_ref,
        target_label=container_ref,
        action=action,
        trigger_type="manual",
    )

    def execute() -> None:
        try:
            _execute_container_step(run_id, 1, container_ref, action)
            database.finish_action_run(run_id, "success")
        except Exception as exc:
            _finish_run_failed(run_id, exc)

    if background:
        _run_async(execute)
    else:
        execute()
    return run_id


def start_group_run(group_id: int, action: str, background: bool = True) -> int:
    group = database.get_group(group_id)
    if not group:
        raise DockerOperationError("Group was not found.")

    run_id = database.create_action_run(
        source_type="group",
        source_id=str(group_id),
        target_label=group["name"],
        action=action,
        trigger_type="manual",
    )

    def execute() -> None:
        try:
            _execute_group_steps(run_id, group, action)
            database.finish_action_run(run_id, "success")
        except Exception as exc:
            _finish_run_failed(run_id, exc)

    if background:
        _run_async(execute)
    else:
        execute()
    return run_id


def start_schedule_run(schedule_id: int, trigger_type: str, background: bool = True) -> int:
    schedule = database.get_schedule(schedule_id)
    if not schedule:
        raise DockerOperationError("Schedule was not found.")

    run_id = database.create_action_run(
        source_type="schedule",
        source_id=str(schedule_id),
        target_label=schedule["name"],
        action=schedule["action"],
        trigger_type=trigger_type,
        schedule_id=schedule_id,
    )

    def execute() -> None:
        try:
            if schedule["target_type"] == "container":
                _execute_container_step(run_id, 1, schedule["target_id"], schedule["action"])
            elif schedule["target_type"] == "group":
                group = database.get_group(int(schedule["target_id"]))
                if not group:
                    raise DockerOperationError("Schedule group target was not found.")
                _execute_group_steps(run_id, group, schedule["action"])
            else:
                raise DockerOperationError("Invalid schedule target.")
            database.finish_action_run(run_id, "success")
        except Exception as exc:
            _finish_run_failed(run_id, exc)

    if background:
        _run_async(execute)
    else:
        execute()
    return run_id
