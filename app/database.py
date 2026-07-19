from __future__ import annotations

import json
import os
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


DB_PATH = Path(os.getenv("APP_DB", "/app/data/app.db"))
SCHEMA_VERSION = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _row(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def _rows(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    if not _table_exists(conn, table):
        return False
    return column in {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if not _column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _backup_before_migration() -> Path | None:
    if not DB_PATH.exists() or DB_PATH.stat().st_size == 0:
        return None
    backup_dir = DB_PATH.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"{DB_PATH.stem}.pre-migration-{stamp}{DB_PATH.suffix or '.db'}"
    shutil.copy2(DB_PATH, target)
    return target


def _migration_001_base(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            delay_seconds INTEGER NOT NULL DEFAULT 5,
            requires_nas INTEGER NOT NULL DEFAULT 0,
            auto_start_on_nas_online INTEGER NOT NULL DEFAULT 0,
            auto_stop_on_nas_offline INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS group_containers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            container_id TEXT NOT NULL,
            container_name TEXT,
            position INTEGER NOT NULL,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
            UNIQUE (group_id, container_id)
        );

        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            target_type TEXT NOT NULL CHECK (target_type IN ('container', 'group')),
            target_id TEXT NOT NULL,
            action TEXT NOT NULL CHECK (action IN ('start', 'stop', 'restart')),
            hour INTEGER NOT NULL CHECK (hour BETWEEN 0 AND 23),
            minute INTEGER NOT NULL CHECK (minute BETWEEN 0 AND 59),
            weekdays TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            require_nas INTEGER NOT NULL DEFAULT 0,
            last_run_at TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS action_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            target_label TEXT NOT NULL,
            action TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            status TEXT NOT NULL,
            schedule_id INTEGER,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS action_run_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            target_type TEXT NOT NULL,
            target_name TEXT NOT NULL,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            FOREIGN KEY (run_id) REFERENCES action_runs(id) ON DELETE CASCADE
        );
        """
    )
    _ensure_column(conn, "group_containers", "container_name", "TEXT")
    _ensure_column(conn, "groups", "requires_nas", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "groups", "auto_start_on_nas_online", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "groups", "auto_stop_on_nas_offline", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "schedules", "require_nas", "INTEGER NOT NULL DEFAULT 0")


def _migration_002_scheduler_modernization(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS nas_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            enabled INTEGER NOT NULL DEFAULT 1,
            host TEXT NOT NULL DEFAULT '',
            check_interval_seconds INTEGER NOT NULL DEFAULT 60,
            mount_paths TEXT NOT NULL DEFAULT '',
            mac_address TEXT NOT NULL DEFAULT '',
            wol_enabled INTEGER NOT NULL DEFAULT 0,
            auto_wake INTEGER NOT NULL DEFAULT 0,
            wake_wait_seconds INTEGER NOT NULL DEFAULT 30,
            last_ready INTEGER NOT NULL DEFAULT 0,
            last_host_online INTEGER NOT NULL DEFAULT 0,
            last_mounts_ok INTEGER NOT NULL DEFAULT 0,
            last_checked_at TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            last_automation_ready INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS webhooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'generic',
            url TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            events TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS action_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            target_label TEXT NOT NULL,
            action TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            error TEXT
        );
        """
    )
    _ensure_column(conn, "groups", "nas_profile_id", "INTEGER")
    _ensure_column(conn, "groups", "favorite", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "groups", "error_policy", "TEXT NOT NULL DEFAULT 'stop'")
    _ensure_column(conn, "groups", "conflict_policy", "TEXT NOT NULL DEFAULT 'skip'")
    _ensure_column(conn, "groups", "wait_for_healthy", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "groups", "health_timeout_seconds", "INTEGER NOT NULL DEFAULT 60")
    _ensure_column(conn, "group_containers", "delay_seconds", "INTEGER")
    _ensure_column(conn, "schedules", "nas_profile_id", "INTEGER")
    _ensure_column(conn, "schedules", "conflict_policy", "TEXT NOT NULL DEFAULT 'skip'")
    _ensure_column(conn, "action_runs", "cancel_requested", "INTEGER NOT NULL DEFAULT 0")

    # Preserve the legacy single-NAS configuration as a default profile on upgrade.
    existing = conn.execute("SELECT COUNT(*) AS count FROM nas_profiles").fetchone()["count"]
    if existing == 0 and _table_exists(conn, "app_settings"):
        settings = {
            row["key"]: row["value"]
            for row in conn.execute("SELECT key, value FROM app_settings WHERE key LIKE 'nas_%'").fetchall()
        }
        if settings.get("nas_host") or settings.get("nas_enabled") == "1":
            now = _now()
            cursor = conn.execute(
                """
                INSERT INTO nas_profiles (
                    name, enabled, host, check_interval_seconds, mount_paths,
                    last_ready, last_host_online, last_mounts_ok, last_checked_at,
                    last_error, last_automation_ready, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Default NAS",
                    1 if settings.get("nas_enabled") == "1" else 0,
                    settings.get("nas_host", ""),
                    int(settings.get("nas_check_interval_seconds", "60") or 60),
                    settings.get("nas_mount_paths", ""),
                    1 if settings.get("nas_last_ready") == "1" else 0,
                    1 if settings.get("nas_last_host_online") == "1" else 0,
                    1 if settings.get("nas_last_mounts_ok") == "1" else 0,
                    settings.get("nas_last_checked_at", ""),
                    settings.get("nas_last_error", ""),
                    1 if settings.get("nas_last_automation_ready") == "1" else 0,
                    now,
                    now,
                ),
            )
            profile_id = int(cursor.lastrowid)
            conn.execute("UPDATE groups SET nas_profile_id = ? WHERE requires_nas = 1", (profile_id,))
            conn.execute("UPDATE schedules SET nas_profile_id = ? WHERE require_nas = 1", (profile_id,))


_MIGRATIONS = {
    1: _migration_001_base,
    2: _migration_002_scheduler_modernization,
}


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        current = conn.execute("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations").fetchone()["version"]

    if current < SCHEMA_VERSION and DB_PATH.exists() and DB_PATH.stat().st_size:
        _backup_before_migration()

    with get_connection() as conn:
        for version in range(current + 1, SCHEMA_VERSION + 1):
            migration = _MIGRATIONS[version]
            with conn:
                migration(conn)
                conn.execute(
                    "INSERT OR REPLACE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (version, _now()),
                )
        _ensure_default_settings(conn)


def _ensure_default_settings(conn: sqlite3.Connection) -> None:
    defaults = {
        "nas_enabled": "0",
        "nas_host": "",
        "nas_check_interval_seconds": "60",
        "nas_mount_paths": "",
        "nas_last_ready": "0",
        "nas_last_host_online": "0",
        "nas_last_mounts_ok": "0",
        "nas_last_checked_at": "",
        "nas_last_error": "",
        "nas_last_automation_ready": "0",
        "log_retention_days": "30",
    }
    for key, value in defaults.items():
        conn.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", (key, value))


def list_groups() -> list[dict]:
    with get_connection() as conn:
        groups = _rows(conn.execute("SELECT * FROM groups ORDER BY favorite DESC, name").fetchall())
        for group in groups:
            group["containers"] = _rows(
                conn.execute(
                    "SELECT * FROM group_containers WHERE group_id = ? ORDER BY position ASC, id ASC",
                    (group["id"],),
                ).fetchall()
            )
        return groups


def get_group(group_id: int) -> dict | None:
    with get_connection() as conn:
        group = _row(conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone())
        if not group:
            return None
        group["containers"] = _rows(
            conn.execute(
                "SELECT * FROM group_containers WHERE group_id = ? ORDER BY position ASC, id ASC",
                (group_id,),
            ).fetchall()
        )
        return group


def _replace_group_containers(conn: sqlite3.Connection, group_id: int, containers: list[tuple]) -> None:
    conn.execute("DELETE FROM group_containers WHERE group_id = ?", (group_id,))
    for index, item in enumerate(containers, start=1):
        container_name = item[0]
        container_id = item[1]
        position = item[2] if len(item) > 2 else index
        delay_seconds = item[3] if len(item) > 3 else None
        conn.execute(
            """
            INSERT INTO group_containers (group_id, container_id, container_name, position, delay_seconds)
            VALUES (?, ?, ?, ?, ?)
            """,
            (group_id, container_id, container_name, position or index, delay_seconds),
        )


def create_group(
    name: str,
    delay_seconds: int,
    containers: list[tuple],
    requires_nas: bool = False,
    auto_start_on_nas_online: bool = False,
    auto_stop_on_nas_offline: bool = False,
    **options,
) -> int:
    now = _now()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO groups (
                name, delay_seconds, requires_nas, auto_start_on_nas_online,
                auto_stop_on_nas_offline, nas_profile_id, favorite, error_policy,
                conflict_policy, wait_for_healthy, health_timeout_seconds, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                delay_seconds,
                1 if requires_nas else 0,
                1 if auto_start_on_nas_online else 0,
                1 if auto_stop_on_nas_offline else 0,
                options.get("nas_profile_id"),
                1 if options.get("favorite") else 0,
                options.get("error_policy", "stop"),
                options.get("conflict_policy", "skip"),
                1 if options.get("wait_for_healthy") else 0,
                int(options.get("health_timeout_seconds", 60)),
                now,
                now,
            ),
        )
        group_id = int(cursor.lastrowid)
        _replace_group_containers(conn, group_id, containers)
        return group_id


def update_group(
    group_id: int,
    name: str,
    delay_seconds: int,
    containers: list[tuple],
    requires_nas: bool = False,
    auto_start_on_nas_online: bool = False,
    auto_stop_on_nas_offline: bool = False,
    **options,
) -> None:
    current = get_group(group_id) or {}
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE groups SET
                name = ?, delay_seconds = ?, requires_nas = ?,
                auto_start_on_nas_online = ?, auto_stop_on_nas_offline = ?,
                nas_profile_id = ?, favorite = ?, error_policy = ?, conflict_policy = ?,
                wait_for_healthy = ?, health_timeout_seconds = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                name,
                delay_seconds,
                1 if requires_nas else 0,
                1 if auto_start_on_nas_online else 0,
                1 if auto_stop_on_nas_offline else 0,
                options.get("nas_profile_id", current.get("nas_profile_id")),
                1 if options.get("favorite", current.get("favorite")) else 0,
                options.get("error_policy", current.get("error_policy", "stop")),
                options.get("conflict_policy", current.get("conflict_policy", "skip")),
                1 if options.get("wait_for_healthy", current.get("wait_for_healthy")) else 0,
                int(options.get("health_timeout_seconds", current.get("health_timeout_seconds", 60))),
                _now(),
                group_id,
            ),
        )
        _replace_group_containers(conn, group_id, containers)


def delete_group(group_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        conn.execute("DELETE FROM schedules WHERE target_type = 'group' AND target_id = ?", (str(group_id),))


def set_group_container_name(group_container_id: int, container_name: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE group_containers SET container_name = ? WHERE id = ?", (container_name, group_container_id))


def list_schedules() -> list[dict]:
    with get_connection() as conn:
        return _rows(
            conn.execute("SELECT * FROM schedules ORDER BY enabled DESC, hour ASC, minute ASC, name ASC").fetchall()
        )


def list_enabled_schedules() -> list[dict]:
    with get_connection() as conn:
        return _rows(conn.execute("SELECT * FROM schedules WHERE enabled = 1").fetchall())


def get_schedule(schedule_id: int) -> dict | None:
    with get_connection() as conn:
        return _row(conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone())


def create_schedule(
    name: str,
    target_type: str,
    target_id: str,
    action: str,
    hour: int,
    minute: int,
    weekdays: str,
    enabled: bool,
    require_nas: bool = False,
    **options,
) -> int:
    now = _now()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO schedules (
                name, target_type, target_id, action, hour, minute, weekdays,
                enabled, require_nas, nas_profile_id, conflict_policy, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name, target_type, target_id, action, hour, minute, weekdays,
                1 if enabled else 0, 1 if require_nas else 0,
                options.get("nas_profile_id"), options.get("conflict_policy", "skip"), now, now,
            ),
        )
        return int(cursor.lastrowid)


def update_schedule(
    schedule_id: int,
    name: str,
    target_type: str,
    target_id: str,
    action: str,
    hour: int,
    minute: int,
    weekdays: str,
    enabled: bool,
    require_nas: bool = False,
    **options,
) -> None:
    current = get_schedule(schedule_id) or {}
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE schedules SET
                name = ?, target_type = ?, target_id = ?, action = ?, hour = ?, minute = ?,
                weekdays = ?, enabled = ?, require_nas = ?, nas_profile_id = ?, conflict_policy = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                name, target_type, target_id, action, hour, minute, weekdays, 1 if enabled else 0,
                1 if require_nas else 0, options.get("nas_profile_id", current.get("nas_profile_id")),
                options.get("conflict_policy", current.get("conflict_policy", "skip")), _now(), schedule_id,
            ),
        )


def get_setting(key: str, default: str = "") -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default


def set_setting(key: str, value: str) -> None:
    set_settings({key: value})


def set_settings(values: dict[str, str]) -> None:
    with get_connection() as conn:
        for key, value in values.items():
            conn.execute(
                "INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )


def get_nas_settings() -> dict[str, str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM app_settings WHERE key LIKE 'nas_%'").fetchall()
        settings = {row["key"]: row["value"] for row in rows}
    defaults = {
        "nas_enabled": "0", "nas_host": "", "nas_check_interval_seconds": "60", "nas_mount_paths": "",
        "nas_last_ready": "0", "nas_last_host_online": "0", "nas_last_mounts_ok": "0",
        "nas_last_checked_at": "", "nas_last_error": "", "nas_last_automation_ready": "0",
    }
    defaults.update(settings)
    return defaults


def list_nas_profiles() -> list[dict]:
    with get_connection() as conn:
        return _rows(conn.execute("SELECT * FROM nas_profiles ORDER BY name").fetchall())


def get_nas_profile(profile_id: int) -> dict | None:
    with get_connection() as conn:
        return _row(conn.execute("SELECT * FROM nas_profiles WHERE id = ?", (profile_id,)).fetchone())


def save_nas_profile(profile_id: int | None, values: dict) -> int:
    now = _now()
    fields = (
        values.get("name", "NAS").strip() or "NAS",
        1 if values.get("enabled", True) else 0,
        values.get("host", "").strip(),
        max(10, int(values.get("check_interval_seconds", 60))),
        values.get("mount_paths", "").strip(),
        values.get("mac_address", "").strip(),
        1 if values.get("wol_enabled") else 0,
        1 if values.get("auto_wake") else 0,
        max(1, int(values.get("wake_wait_seconds", 30))),
    )
    with get_connection() as conn:
        if profile_id is None:
            cursor = conn.execute(
                """
                INSERT INTO nas_profiles (
                    name, enabled, host, check_interval_seconds, mount_paths, mac_address,
                    wol_enabled, auto_wake, wake_wait_seconds, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*fields, now, now),
            )
            return int(cursor.lastrowid)
        conn.execute(
            """
            UPDATE nas_profiles SET name=?, enabled=?, host=?, check_interval_seconds=?, mount_paths=?,
                mac_address=?, wol_enabled=?, auto_wake=?, wake_wait_seconds=?, updated_at=? WHERE id=?
            """,
            (*fields, now, profile_id),
        )
        return profile_id


def update_nas_profile_status(profile_id: int, **status) -> None:
    allowed = {
        "last_ready", "last_host_online", "last_mounts_ok", "last_checked_at",
        "last_error", "last_automation_ready",
    }
    updates = {key: value for key, value in status.items() if key in allowed}
    if not updates:
        return
    assignments = ", ".join(f"{key} = ?" for key in updates)
    values = [int(value) if key.startswith("last_") and key in {"last_ready", "last_host_online", "last_mounts_ok", "last_automation_ready"} else value for key, value in updates.items()]
    with get_connection() as conn:
        conn.execute(f"UPDATE nas_profiles SET {assignments}, updated_at = ? WHERE id = ?", (*values, _now(), profile_id))


def delete_nas_profile(profile_id: int) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE groups SET nas_profile_id = NULL, requires_nas = 0 WHERE nas_profile_id = ?", (profile_id,))
        conn.execute("UPDATE schedules SET nas_profile_id = NULL, require_nas = 0 WHERE nas_profile_id = ?", (profile_id,))
        conn.execute("DELETE FROM nas_profiles WHERE id = ?", (profile_id,))


def set_schedule_enabled(schedule_id: int, enabled: bool) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE schedules SET enabled = ?, updated_at = ? WHERE id = ?", (1 if enabled else 0, _now(), schedule_id))


def delete_schedule(schedule_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))


def mark_schedule_run(schedule_id: int, error: str | None) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE schedules SET last_run_at = ?, last_error = ?, updated_at = ? WHERE id = ?",
            (_now(), error, _now(), schedule_id),
        )


def create_action_run(source_type: str, source_id: str, target_label: str, action: str, trigger_type: str, schedule_id: int | None = None) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO action_runs (source_type, source_id, target_label, action, trigger_type, status, schedule_id, started_at)
            VALUES (?, ?, ?, ?, ?, 'running', ?, ?)
            """,
            (source_type, source_id, target_label, action, trigger_type, schedule_id, _now()),
        )
        return int(cursor.lastrowid)


def finish_action_run(run_id: int, status: str, error: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE action_runs SET status = ?, error = ?, finished_at = ? WHERE id = ?", (status, error, _now(), run_id))


def request_action_run_cancel(run_id: int) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE action_runs SET cancel_requested = 1 WHERE id = ? AND status = 'running'", (run_id,))


def is_action_run_cancel_requested(run_id: int) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT cancel_requested FROM action_runs WHERE id = ?", (run_id,)).fetchone()
        return bool(row and row["cancel_requested"])


def find_running_actions_for_targets(target_names: list[str]) -> list[dict]:
    if not target_names:
        return []
    placeholders = ",".join("?" for _ in target_names)
    with get_connection() as conn:
        return _rows(
            conn.execute(
                f"""
                SELECT DISTINCT r.* FROM action_runs r
                LEFT JOIN action_run_steps s ON s.run_id = r.id
                WHERE r.status = 'running' AND (r.target_label IN ({placeholders}) OR s.target_name IN ({placeholders}))
                """,
                (*target_names, *target_names),
            ).fetchall()
        )


def create_action_step(run_id: int, position: int, target_type: str, target_name: str, action: str) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO action_run_steps (run_id, position, target_type, target_name, action, status, started_at)
            VALUES (?, ?, ?, ?, ?, 'running', ?)
            """,
            (run_id, position, target_type, target_name, action, _now()),
        )
        return int(cursor.lastrowid)


def finish_action_step(step_id: int, status: str, message: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE action_run_steps SET status = ?, message = ?, finished_at = ? WHERE id = ?",
            (status, message, _now(), step_id),
        )


def get_action_run(run_id: int) -> dict | None:
    with get_connection() as conn:
        return _row(conn.execute("SELECT * FROM action_runs WHERE id = ?", (run_id,)).fetchone())


def get_action_run_steps(run_id: int) -> list[dict]:
    with get_connection() as conn:
        return _rows(conn.execute("SELECT * FROM action_run_steps WHERE run_id = ? ORDER BY position ASC, id ASC", (run_id,)).fetchall())


def list_action_runs(source_type: str | None = None, source_id: str | None = None, schedule_id: int | None = None, trigger_prefix: str | None = None, limit: int = 20) -> list[dict]:
    clauses: list[str] = []
    params: list[object] = []
    if source_type:
        clauses.append("source_type = ?")
        params.append(source_type)
    if source_id:
        clauses.append("source_id = ?")
        params.append(source_id)
    if schedule_id is not None:
        clauses.append("schedule_id = ?")
        params.append(schedule_id)
    if trigger_prefix:
        clauses.append("trigger_type LIKE ?")
        params.append(f"{trigger_prefix}%")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    with get_connection() as conn:
        return _rows(
            conn.execute(
                f"SELECT * FROM action_runs {where} ORDER BY started_at DESC, id DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        )


def compact_old_action_runs(retention_days: int | None = None) -> int:
    days = retention_days or max(1, int(get_setting("log_retention_days", "30") or 30))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    with get_connection() as conn:
        old = conn.execute("SELECT * FROM action_runs WHERE started_at < ?", (cutoff,)).fetchall()
        for run in old:
            conn.execute(
                """
                INSERT INTO action_history (source_type, source_id, target_label, action, trigger_type, status, started_at, finished_at, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run["source_type"], run["source_id"], run["target_label"], run["action"], run["trigger_type"],
                    run["status"], run["started_at"], run["finished_at"], run["error"],
                ),
            )
            conn.execute("DELETE FROM action_runs WHERE id = ?", (run["id"],))
        return len(old)


def export_configuration() -> str:
    with get_connection() as conn:
        payload = {
            "format": 1,
            "exported_at": _now(),
            "settings": _rows(conn.execute("SELECT key, value FROM app_settings ORDER BY key").fetchall()),
            "groups": _rows(conn.execute("SELECT * FROM groups ORDER BY id").fetchall()),
            "group_containers": _rows(conn.execute("SELECT * FROM group_containers ORDER BY group_id, position, id").fetchall()),
            "schedules": _rows(conn.execute("SELECT * FROM schedules ORDER BY id").fetchall()),
            "nas_profiles": _rows(conn.execute("SELECT * FROM nas_profiles ORDER BY id").fetchall()),
            "webhooks": _rows(conn.execute("SELECT * FROM webhooks ORDER BY id").fetchall()),
        }
    return json.dumps(payload, indent=2, sort_keys=True)
