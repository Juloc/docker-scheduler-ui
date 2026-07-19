import threading
import time
from typing import Callable

from app import database, nas_service
from app.docker_ops import DockerOperationError, run_container_action


NAS_GATED_GROUP_ACTIONS = {"start", "restart"}


def _run_async(target: Callable[[], None]) -> None:
    thread = threading.Thread(target=target, daemon=True)
    thread.start()


def _finish_run_failed(run_id: int, exc: Exception) -> None:
    database.finish_action_run(run_id, "failed", str(exc))


def _finish_run_skipped(run_id: int, message: str) -> None:
    database.finish_action_run(run_id, "skipped", message)


def _container_ref(item: dict) -> str:
    return item.get("container_name") or item.get("container_id") or ""


def _ordered_group_items(group: dict, action: str) -> list[dict]:
    """Return the execution order for a group action.

    Start/restart use the configured dependency order. Stop runs in reverse so
    dependants are stopped before the services they depend on.
    """
    items = list(group.get("containers", []))
    if action == "stop":
        items.reverse()
    return items


def _execute_container_step(run_id: int, position: int, container_ref: str, action: str) -> None:
    step_id = database.create_action_step(run_id, position, "container", container_ref, action)
    try:
        message = run_container_action(container_ref, action)
        database.finish_action_step(step_id, "success", message)
    except Exception as exc:
        database.finish_action_step(step_id, "failed", str(exc))
        raise


def _execute_group_steps(run_id: int, group: dict, action: str) -> None:
    containers = _ordered_group_items(group, action)
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


def _group_requires_nas_gate(group: dict, action: str) -> bool:
    return bool(group.get("requires_nas")) and action in NAS_GATED_GROUP_ACTIONS


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


def start_group_run(
    group_id: int,
    action: str,
    background: bool = True,
    trigger_type: str = "manual",
    check_nas: bool = True,
) -> int:
    group = database.get_group(group_id)
    if not group:
        raise DockerOperationError("Group was not found.")

    run_id = database.create_action_run(
        source_type="group",
        source_id=str(group_id),
        target_label=group["name"],
        action=action,
        trigger_type=trigger_type,
    )

    def execute() -> None:
        try:
            if check_nas and _group_requires_nas_gate(group, action):
                ready, message = nas_service.require_ready()
                if not ready:
                    _finish_run_skipped(run_id, f"NAS is not ready: {message}")
                    return
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
            group = None
            if schedule["target_type"] == "group":
                group = database.get_group(int(schedule["target_id"]))
                if not group:
                    raise DockerOperationError("Schedule group target was not found.")

            if schedule.get("require_nas"):
                ready, message = nas_service.require_ready()
                if not ready:
                    _finish_run_skipped(run_id, f"NAS is not ready: {message}")
                    return
            elif group and _group_requires_nas_gate(group, schedule["action"]):
                ready, message = nas_service.require_ready()
                if not ready:
                    _finish_run_skipped(run_id, f"NAS is not ready: {message}")
                    return

            if schedule["target_type"] == "container":
                _execute_container_step(run_id, 1, schedule["target_id"], schedule["action"])
            elif schedule["target_type"] == "group":
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
