from __future__ import annotations

import platform
import socket
import subprocess
import time
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


def _normalize_profile(profile: dict) -> dict:
    return {
        **profile,
        "enabled": _as_bool(profile.get("enabled")),
        "check_interval_seconds": max(10, _as_int(profile.get("check_interval_seconds"), 60)),
        "mount_paths_text": profile.get("mount_paths", ""),
        "mount_paths": _split_mount_paths(profile.get("mount_paths", "")),
        "wol_enabled": _as_bool(profile.get("wol_enabled")),
        "auto_wake": _as_bool(profile.get("auto_wake")),
        "wake_wait_seconds": max(1, _as_int(profile.get("wake_wait_seconds"), 30)),
        "ready": _as_bool(profile.get("last_ready")),
        "host_online": _as_bool(profile.get("last_host_online")),
        "mounts_ok": _as_bool(profile.get("last_mounts_ok")),
        "last_checked_at": profile.get("last_checked_at", ""),
        "last_error": profile.get("last_error", ""),
    }


def list_profiles() -> list[dict]:
    return [_normalize_profile(profile) for profile in database.list_nas_profiles()]


def get_profile(profile_id: int | None) -> dict | None:
    if profile_id:
        profile = database.get_nas_profile(int(profile_id))
        return _normalize_profile(profile) if profile else None
    profiles = list_profiles()
    return profiles[0] if profiles else None


def _legacy_status() -> dict:
    settings = database.get_nas_settings()
    return {
        "id": None,
        "name": "Default NAS",
        "enabled": _as_bool(settings.get("nas_enabled")),
        "host": settings.get("nas_host", ""),
        "check_interval_seconds": max(10, _as_int(settings.get("nas_check_interval_seconds"), 60)),
        "mount_paths_text": settings.get("nas_mount_paths", ""),
        "mount_paths": _split_mount_paths(settings.get("nas_mount_paths", "")),
        "mac_address": "",
        "wol_enabled": False,
        "auto_wake": False,
        "wake_wait_seconds": 30,
        "ready": _as_bool(settings.get("nas_last_ready")),
        "host_online": _as_bool(settings.get("nas_last_host_online")),
        "mounts_ok": _as_bool(settings.get("nas_last_mounts_ok")),
        "last_checked_at": settings.get("nas_last_checked_at", ""),
        "last_error": settings.get("nas_last_error", ""),
    }


def current_status(profile_id: int | None = None) -> dict:
    return get_profile(profile_id) or _legacy_status()


def update_settings(enabled: bool, host: str, check_interval_seconds: int, mount_paths_text: str) -> None:
    """Compatibility path for the legacy single-NAS settings form."""
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

    profile = get_profile(None)
    database.save_nas_profile(
        profile.get("id") if profile else None,
        {
            "name": profile.get("name", "Default NAS") if profile else "Default NAS",
            "enabled": enabled,
            "host": host,
            "check_interval_seconds": check_interval_seconds,
            "mount_paths": mount_paths_text,
            "mac_address": profile.get("mac_address", "") if profile else "",
            "wol_enabled": profile.get("wol_enabled", False) if profile else False,
            "auto_wake": profile.get("auto_wake", False) if profile else False,
            "wake_wait_seconds": profile.get("wake_wait_seconds", 30) if profile else 30,
        },
    )


def save_profile(profile_id: int | None, values: dict) -> int:
    return database.save_nas_profile(profile_id, values)


def delete_profile(profile_id: int) -> None:
    database.delete_nas_profile(profile_id)


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
    return False, stderr or f"Ping to {host} failed."


def _check_mount_paths(paths: list[str]) -> tuple[bool, str | None]:
    missing = [path for path in paths if not Path(path).exists()]
    if not missing:
        return True, None
    return False, "Missing mount paths: " + ", ".join(missing)


def _normalize_mac(mac_address: str) -> str:
    compact = mac_address.replace(":", "").replace("-", "").replace(".", "").strip()
    if len(compact) != 12:
        raise ValueError("MAC address must contain 12 hexadecimal digits.")
    try:
        bytes.fromhex(compact)
    except ValueError as exc:
        raise ValueError("MAC address is invalid.") from exc
    return compact


def wake(profile_id: int | None = None) -> str:
    profile = current_status(profile_id)
    if not profile.get("wol_enabled"):
        raise ValueError("Wake-on-LAN is not enabled for this NAS profile.")
    mac = _normalize_mac(str(profile.get("mac_address") or ""))
    packet = bytes.fromhex("FF" * 6 + mac * 16)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(2)
        sock.sendto(packet, ("255.255.255.255", 9))
    return f"Wake-on-LAN packet sent to {profile.get('name') or profile.get('host') or mac}."


def check_status(profile_id: int | None = None) -> dict:
    previous = current_status(profile_id)
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
    else:
        host_online, ping_error = _ping_host(previous["host"])
        mounts_ok, mount_error = _check_mount_paths(previous["mount_paths"])
        ready = host_online and mounts_ok
        status = {
            **previous,
            "ready": ready,
            "host_online": host_online,
            "mounts_ok": mounts_ok,
            "last_checked_at": checked_at,
            "last_error": ping_error or mount_error or "",
            "previous_ready": previous["ready"],
        }

    if previous.get("id"):
        database.update_nas_profile_status(
            int(previous["id"]),
            last_ready=status["ready"],
            last_host_online=status["host_online"],
            last_mounts_ok=status["mounts_ok"],
            last_checked_at=checked_at,
            last_error=status["last_error"],
        )
    else:
        database.set_settings(
            {
                "nas_last_ready": "1" if status["ready"] else "0",
                "nas_last_host_online": "1" if status["host_online"] else "0",
                "nas_last_mounts_ok": "1" if status["mounts_ok"] else "0",
                "nas_last_checked_at": checked_at,
                "nas_last_error": status["last_error"],
            }
        )
    return status


def require_ready(profile_id: int | None = None, auto_wake: bool = False) -> tuple[bool, str]:
    status = current_status(profile_id)
    if not status["enabled"]:
        return False, "NAS checks are disabled."

    status = check_status(profile_id)
    if status["ready"]:
        return True, "NAS is ready."

    if auto_wake and status.get("wol_enabled") and status.get("auto_wake") and not status["host_online"]:
        try:
            wake(profile_id)
        except ValueError as exc:
            return False, str(exc)
        deadline = time.monotonic() + status.get("wake_wait_seconds", 30)
        while time.monotonic() < deadline:
            time.sleep(min(2, max(0.1, deadline - time.monotonic())))
            status = check_status(profile_id)
            if status["ready"]:
                return True, "NAS was woken and is ready."

    if not status["host_online"]:
        return False, status["last_error"] or f"NAS host {status['host']} is not reachable."
    if not status["mounts_ok"]:
        return False, status["last_error"] or "NAS mount check failed."
    return False, "NAS is not ready."


def dependent_groups(auto_start_only: bool = False, auto_stop_only: bool = False, profile_id: int | None = None) -> list[dict]:
    groups = []
    for group in database.list_groups():
        if not group.get("requires_nas"):
            continue
        if profile_id is not None and group.get("nas_profile_id") != profile_id:
            continue
        if auto_start_only and not group.get("auto_start_on_nas_online"):
            continue
        if auto_stop_only and not group.get("auto_stop_on_nas_offline"):
            continue
        groups.append(group)
    return groups
