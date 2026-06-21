import time
from typing import Any

import docker
from docker.errors import APIError, DockerException, NotFound

from app import database


VALID_ACTIONS = {"start", "stop", "restart"}


class DockerOperationError(RuntimeError):
    pass


def _client() -> docker.DockerClient:
    try:
        return docker.from_env()
    except DockerException as exc:
        raise DockerOperationError(f"Could not create Docker client: {exc}") from exc


def _close_client(client: docker.DockerClient | None) -> None:
    if client:
        try:
            client.close()
        except DockerException:
            pass


def _image_name(container: Any) -> str:
    tags = getattr(container.image, "tags", None) or []
    if tags:
        return ", ".join(tags)
    return getattr(container.image, "short_id", "-")


def _format_ports(ports: dict | None) -> str:
    if not ports:
        return "-"

    parts: list[str] = []
    for private_port, mappings in sorted(ports.items()):
        if not mappings:
            parts.append(private_port)
            continue
        for mapping in mappings:
            host_ip = mapping.get("HostIp") or "0.0.0.0"
            host_port = mapping.get("HostPort") or ""
            parts.append(f"{host_ip}:{host_port}->{private_port}")
    return ", ".join(parts) if parts else "-"


def _restart_policy(attrs: dict) -> str:
    policy = attrs.get("HostConfig", {}).get("RestartPolicy", {}) or {}
    name = policy.get("Name") or "no"
    retries = policy.get("MaximumRetryCount")
    if retries:
        return f"{name} ({retries})"
    return name


def _health(attrs: dict) -> str:
    health = attrs.get("State", {}).get("Health")
    if not health:
        return "-"
    return health.get("Status") or "-"


def _container_info(container: Any) -> dict:
    attrs = container.attrs
    state = attrs.get("State", {})
    return {
        "id": container.id,
        "short_id": container.short_id,
        "name": container.name,
        "image": _image_name(container),
        "status": state.get("Status") or container.status,
        "health": _health(attrs),
        "ports": _format_ports(attrs.get("NetworkSettings", {}).get("Ports")),
        "restart_policy": _restart_policy(attrs),
    }


def list_containers() -> list[dict]:
    client = _client()
    try:
        containers = client.containers.list(all=True)
        return sorted((_container_info(container) for container in containers), key=lambda item: item["name"])
    except DockerException as exc:
        raise DockerOperationError(f"Could not read Docker containers: {exc}") from exc
    finally:
        _close_client(client)


def get_container_info(container_id: str) -> dict:
    client = _client()
    try:
        return _container_info(client.containers.get(container_id))
    except NotFound as exc:
        raise DockerOperationError("Container was not found.") from exc
    except DockerException as exc:
        raise DockerOperationError(f"Could not read container: {exc}") from exc
    finally:
        _close_client(client)


def run_container_action(
    container_id: str,
    action: str,
    client: docker.DockerClient | None = None,
) -> str:
    if action not in VALID_ACTIONS:
        raise DockerOperationError("Invalid action.")

    owns_client = client is None
    active_client = client or _client()
    try:
        container = active_client.containers.get(container_id)
        if action == "start":
            container.start()
        elif action == "stop":
            container.stop()
        elif action == "restart":
            container.restart()
        return f"{action} completed for {container.name}."
    except NotFound as exc:
        raise DockerOperationError("Container was not found.") from exc
    except APIError as exc:
        explanation = getattr(exc, "explanation", None) or str(exc)
        raise DockerOperationError(f"Docker error: {explanation}") from exc
    except DockerException as exc:
        raise DockerOperationError(f"Docker error: {exc}") from exc
    finally:
        if owns_client:
            _close_client(active_client)


def run_group_action(group_id: int, action: str) -> str:
    if action not in VALID_ACTIONS:
        raise DockerOperationError("Invalid action.")

    group = database.get_group(group_id)
    if not group:
        raise DockerOperationError("Group was not found.")
    if not group["containers"]:
        raise DockerOperationError("Group contains no containers.")

    client = _client()
    messages: list[str] = []
    delay_seconds = max(0, int(group["delay_seconds"] or 0))

    try:
        for index, item in enumerate(group["containers"]):
            container_ref = item.get("container_name") or item["container_id"]
            messages.append(run_container_action(container_ref, action, client=client))
            if delay_seconds and index < len(group["containers"]) - 1:
                time.sleep(delay_seconds)
        return " ".join(messages)
    finally:
        _close_client(client)


def get_container_logs(container_id: str, tail: int = 100) -> tuple[dict, str]:
    client = _client()
    try:
        container = client.containers.get(container_id)
        logs = container.logs(tail=tail, stdout=True, stderr=True)
        return _container_info(container), logs.decode("utf-8", errors="replace")
    except NotFound as exc:
        raise DockerOperationError("Container was not found.") from exc
    except APIError as exc:
        explanation = getattr(exc, "explanation", None) or str(exc)
        raise DockerOperationError(f"Could not read Docker logs: {explanation}") from exc
    except DockerException as exc:
        raise DockerOperationError(f"Could not read Docker logs: {exc}") from exc
    finally:
        _close_client(client)
