import threading
import time
from typing import Callable

from app import database, nas_service
from app.docker_ops import DockerOperationError, run_container_action, wait_for_container_healthy


NAS_GATED_GROUP_ACTIONS = {"start", "restart"}
CONFLICT_SKIP = "skip"
CONFLICT_CANCEL_AND_START = "cancel_and_start"


class RunCancelled(RuntimeError):
    pass


def _run_async(target: Callable[[], None]) -> None:
    thread = threading.Thread(target=target, daemon=True)
    thread.start()


def _finish_run_failed(run_id: int, exc: Exception) -> None:
    database.finish_action_run(run_id, "failed", str(exc))


def _finish_run_skipped(run_id: int, message: str) -> None:
    database.finish_action_run(run_id, "skipped", message)


def _finish_run_cancelled(run_id: int, message: str = "Run was cancelled.") -> None:
    database.finish_action_run(run_id, "cancelled", message)


def _container_ref(item: dict) -> str:
    return item.get("container_name") or item.get("container_id") or ""


def _ordered_group_items(group: dict, action: str) -> list[dict]:
    items = list(group.get("containers", []))
    if action == "stop":
        items.reverse()
    return items


def _target_refs(group: dict) -> list[str]:
    return [ref for ref in (_container_ref(item) for item in group.get("containers", [])) if ref]


def _check_cancelled(run_id: int) -> None:
    if database.is_action_run_cancel_requested(run_id):
        raise RunCancelled("Run was cancelled before the next container action.")


def _interruptible_sleep(run_id: int, seconds: int) -> None:
    deadline = time.monotonic() + max(0, seconds)
    while time.monotonic() < deadline:
        _check_cancelled(run_id)
        time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))


def _apply_conflict_policy(targets: list[str], policy: str, exclude_run_id: int | None = None) -> tuple[bool, str]:
    conflicts = [run for run in database.find_running_actions_for_targets(targets) if run["id"] != exclude_run_id]
    if not conflicts:
        return True, ""

    if policy != CONFLICT_CANCEL_AND_START:
        return False, "Skipped because one or more target containers are already controlled by a running action."

    for run in conflicts:
        database.request_action_run_cancel(run["id"])

    deadline = time.monotonic() + 15
    conflict_ids = {run["id"] for run in conflicts}
    while time.monotonic() < deadline:
        remaining = [run for run in database.find_running_actions_for_targets(targets) if run["id"] in conflict_ids]
        if not remaining:
            return True, "Cancelled the previous conflicting run."
        time.sleep(0.25)

    return False, "Could not cancel the previous conflicting run before timeout."


def _execute_container_step(run_id: int, position: int, container_ref: str, action: str) -> None:
    _check_cancelled(run_id)
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

    error_policy = str(group.get("error_policy") or "stop")
    wait_for_healthy = bool(group.get("wait_for_healthy")) and action in {"start", "restart"}
    health_timeout = max(1, int(group.get("health_timeout_seconds") or 60))
    failures: list[str] = []

    for index, item in enumerate(containers, start=1):
        _check_cancelled(run_id)
        ref = _container_ref(item)
        if not ref:
            raise DockerOperationError("Group contains a container without name or id.")

        try:
            _execute_container_step(run_id, index, ref, action)
        except RunCancelled:
            raise
        except Exception as exc:
            failures.append(f"{ref}: {exc}")
            if error_policy != "continue":
                raise

        if index >= len(containers):
            continue

        delay_seconds = item.get("delay_seconds")
        if delay_seconds is None:
            delay_seconds = group.get("delay_seconds") or 0
        delay_seconds = max(0, int(delay_seconds))

        if wait_for_healthy and not failures:
            health_result = wait_for_container_healthy(ref, timeout_seconds=health_timeout)
            if health_result == "no-healthcheck" and delay_seconds:
                _interruptible_sleep(run_id, delay_seconds)
        elif delay_seconds:
            _interruptible_sleep(run_id, delay_seconds)

    if failures:
        raise DockerOperationError("Group completed with errors: " + "; ".join(failures))


def _group_requires_nas_gate(group: dict, action: str) -> bool:
    return bool(group.get("requires_nas")) and action in NAS_GATED_GROUP_ACTIONS


def _finish_execution(run_id: int, execute: Callable[[], None]) -> None:
    try:
        execute()
        database.finish_action_run(run_id, "success")
    except RunCancelled as exc:
        _finish_run_cancelled(run_id, str(exc))
    except Exception as exc:
        _finish_run_failed(run_id, exc)


def start_container_run(container_ref: str, action: str, background: bool = True, conflict_policy: str = CONFLICT_SKIP) -> int:
    run_id = database.create_action_run(
        source_type="container",
        source_id=container_ref,
        target_label=container_ref,
        action=action,
        trigger_type="manual",
    )

    def execute() -> None:
        allowed, message = _apply_conflict_policy([container_ref], conflict_policy, exclude_run_id=run_id)
        if not allowed:
            _finish_run_skipped(run_id, message)
            return
        _finish_execution(run_id, lambda: _execute_container_step(run_id, 1, container_ref, action))

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
    conflict_policy: str | None = None,
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
        policy = conflict_policy or group.get("conflict_policy") or CONFLICT_SKIP
        allowed, message = _apply_conflict_policy(_target_refs(group), policy, exclude_run_id=run_id)
        if not allowed:
            _finish_run_skipped(run_id, message)
            return

        def perform() -> None:
            if check_nas and _group_requires_nas_gate(group, action):
                ready, nas_message = nas_service.require_ready(group.get("nas_profile_id"), auto_wake=True)
                if not ready:
                    raise DockerOperationError(f"NAS is not ready: {nas_message}")
            _execute_group_steps(run_id, group, action)

        _finish_execution(run_id, perform)

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
        group = None
        targets = [schedule["target_id"]]
        if schedule["target_type"] == "group":
            group = database.get_group(int(schedule["target_id"]))
            if not group:
                _finish_run_failed(run_id, DockerOperationError("Schedule group target was not found."))
                return
            targets = _target_refs(group)

        allowed, message = _apply_conflict_policy(targets, schedule.get("conflict_policy") or CONFLICT_SKIP, exclude_run_id=run_id)
        if not allowed:
            _finish_run_skipped(run_id, message)
            return

        def perform() -> None:
            profile_id = schedule.get("nas_profile_id") or (group.get("nas_profile_id") if group else None)
            if schedule.get("require_nas") or (group and _group_requires_nas_gate(group, schedule["action"])):
                ready, nas_message = nas_service.require_ready(profile_id, auto_wake=True)
                if not ready:
                    raise DockerOperationError(f"NAS is not ready: {nas_message}")

            if schedule["target_type"] == "container":
                _execute_container_step(run_id, 1, schedule["target_id"], schedule["action"])
            elif schedule["target_type"] == "group":
                _execute_group_steps(run_id, group, schedule["action"])
            else:
                raise DockerOperationError("Invalid schedule target.")

        _finish_execution(run_id, perform)

    if background:
        _run_async(execute)
    else:
        execute()
    return run_id


def cancel_run(run_id: int) -> bool:
    run = database.get_action_run(run_id)
    if not run or run.get("status") != "running":
        return False
    database.request_action_run_cancel(run_id)
    return True
