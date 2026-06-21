import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app import database


DEFAULT_PING_TIMEOUT_SECONDS = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _as_bool(value: object) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def _as_int(value: object, default: int) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _split_mount_paths(value: str) -> list[str]:
    parts: list[str] = []
    normalized = value.replace(";", "\n").replace(",", "\n")
    for line in normalized.splitlines():
        path = line.strip()
        if path:
            parts.append(path)
    return parts


def current_status() -> dict:
    settings = database.get_nas_settings()
    return {
        "enabled": _as_bool(settings.get("nas_enabled")),
        "host": settings.get("nas_host", ""),
        "check_interval_seconds": max(
            10,
            _as_int(settings.get("nas_check_interval_seconds"), 60),
        ),
        "mount_paths_text": settings.get("nas_mount_paths", ""),
        "mount_paths": _split_mount_paths(settings.get("nas_mount_paths", "")),
        "ready": _as_bool(settings.get("nas_last_ready")),
        "host_online": _as_bool(settings.get("nas_last_host_online")),
        "mounts_ok": _as_bool(settings.get("nas_last_mounts_ok")),
        "last_checked_at": settings.get("nas_last_checked_at", ""),
        "last_error": settings.get("nas_last_error", ""),
    }


def update_settings(
    enabled: bool,
    host: str,
    check_interval_seconds: int,
    mount_paths_text: str,
) -> None:
    previous_enabled = current_status()["enabled"]
    values = {
        "nas_enabled": "1" if enabled else "0",
        "nas_host": host.strip(),
        "nas_check_interval_seconds": str(max(10, check_interval_seconds)),
        "nas_mount_paths": mount_paths_text.strip(),
    }
    if not enabled or not previous_enabled:
        values["nas_last_automation_ready"] = "0"
    database.set_settings(values)


def _ping_host(host: str) -> tuple[bool, str | None]:
    if not host:
        return False, "NAS host is empty."

    timeout = DEFAULT_PING_TIMEOUT_SECONDS
    if platform.system().lower().startswith("windows"):
        command = ["ping", "-n", "1", "-w", str(timeout * 1000), host]
    else:
        command = ["ping", "-c", "1", "-W", str(timeout), host]

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout + 1,
            check=False,
        )
    except FileNotFoundError:
        return False, "The ping command is not available in this container."
    except subprocess.TimeoutExpired:
        return False, f"Ping to {host} timed out."

    if result.returncode == 0:
        return True, None

    stderr = (result.stderr or "").strip()
    if stderr:
        return False, stderr
    return False, f"Ping to {host} failed."


def _check_mount_paths(paths: list[str]) -> tuple[bool, str | None]:
    missing = [path for path in paths if not Path(path).exists()]
    if not missing:
        return True, None
    return False, "Missing mount paths: " + ", ".join(missing)


def check_status() -> dict:
    previous = current_status()
    checked_at = _now()

    if not previous["enabled"]:
        status = {
            **previous,
            "ready": False,
            "host_online": False,
            "mounts_ok": True,
            "last_checked_at": checked_at,
            "last_error": "",
            "previous_ready": previous["ready"],
        }
        database.set_settings(
            {
                "nas_last_ready": "0",
                "nas_last_host_online": "0",
                "nas_last_mounts_ok": "1",
                "nas_last_checked_at": checked_at,
                "nas_last_error": "",
            }
        )
        return status

    host_online, ping_error = _ping_host(previous["host"])
    mounts_ok, mount_error = _check_mount_paths(previous["mount_paths"])
    ready = host_online and mounts_ok
    error = ping_error or mount_error or ""

    database.set_settings(
        {
            "nas_last_ready": "1" if ready else "0",
            "nas_last_host_online": "1" if host_online else "0",
            "nas_last_mounts_ok": "1" if mounts_ok else "0",
            "nas_last_checked_at": checked_at,
            "nas_last_error": error,
        }
    )

    return {
        **previous,
        "ready": ready,
        "host_online": host_online,
        "mounts_ok": mounts_ok,
        "last_checked_at": checked_at,
        "last_error": error,
        "previous_ready": previous["ready"],
    }


def require_ready() -> tuple[bool, str]:
    status = current_status()
    if not status["enabled"]:
        return False, "NAS checks are disabled."

    status = check_status()
    if status["ready"]:
        return True, "NAS is ready."

    if not status["host_online"]:
        return False, status["last_error"] or f"NAS host {status['host']} is not reachable."
    if not status["mounts_ok"]:
        return False, status["last_error"] or "NAS mount check failed."
    return False, "NAS is not ready."


def dependent_groups(auto_start_only: bool = False, auto_stop_only: bool = False) -> list[dict]:
    groups = []
    for group in database.list_groups():
        if not group.get("requires_nas"):
            continue
        if auto_start_only and not group.get("auto_start_on_nas_online"):
            continue
        if auto_stop_only and not group.get("auto_stop_on_nas_offline"):
            continue
        groups.append(group)
    return groups
