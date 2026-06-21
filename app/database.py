import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DB_PATH = Path(os.getenv("APP_DB", "/app/data/app.db"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _row(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def _rows(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]


def init_db() -> None:
    with get_connection() as conn:
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
        _ensure_default_settings(conn)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


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
    }
    for key, value in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
            (key, value),
        )


def list_groups() -> list[dict]:
    with get_connection() as conn:
        groups = _rows(conn.execute("SELECT * FROM groups ORDER BY name").fetchall())
        for group in groups:
            group["containers"] = _rows(
                conn.execute(
                    """
                    SELECT * FROM group_containers
                    WHERE group_id = ?
                    ORDER BY position ASC, id ASC
                    """,
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
                """
                SELECT * FROM group_containers
                WHERE group_id = ?
                ORDER BY position ASC, id ASC
                """,
                (group_id,),
            ).fetchall()
        )
        return group


def _replace_group_containers(
    conn: sqlite3.Connection,
    group_id: int,
    containers: list[tuple[str, str, int]],
) -> None:
    conn.execute("DELETE FROM group_containers WHERE group_id = ?", (group_id,))
    for index, (container_name, container_id, position) in enumerate(containers, start=1):
        conn.execute(
            """
            INSERT INTO group_containers (group_id, container_id, container_name, position)
            VALUES (?, ?, ?, ?)
            """,
            (group_id, container_id, container_name, position or index),
        )


def create_group(
    name: str,
    delay_seconds: int,
    containers: list[tuple[str, str, int]],
    requires_nas: bool = False,
    auto_start_on_nas_online: bool = False,
    auto_stop_on_nas_offline: bool = False,
) -> int:
    now = _now()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO groups (
                name, delay_seconds, requires_nas, auto_start_on_nas_online,
                auto_stop_on_nas_offline, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                delay_seconds,
                1 if requires_nas else 0,
                1 if auto_start_on_nas_online else 0,
                1 if auto_stop_on_nas_offline else 0,
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
    containers: list[tuple[str, str, int]],
    requires_nas: bool = False,
    auto_start_on_nas_online: bool = False,
    auto_stop_on_nas_offline: bool = False,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE groups
            SET name = ?, delay_seconds = ?, requires_nas = ?,
                auto_start_on_nas_online = ?, auto_stop_on_nas_offline = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                name,
                delay_seconds,
                1 if requires_nas else 0,
                1 if auto_start_on_nas_online else 0,
                1 if auto_stop_on_nas_offline else 0,
                _now(),
                group_id,
            ),
        )
        _replace_group_containers(conn, group_id, containers)


def delete_group(group_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        conn.execute(
            "DELETE FROM schedules WHERE target_type = 'group' AND target_id = ?",
            (str(group_id),),
        )


def set_group_container_name(group_container_id: int, container_name: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE group_containers SET container_name = ? WHERE id = ?",
            (container_name, group_container_id),
        )


def list_schedules() -> list[dict]:
    with get_connection() as conn:
        return _rows(
            conn.execute(
                """
                SELECT * FROM schedules
                ORDER BY enabled DESC, hour ASC, minute ASC, name ASC
                """
            ).fetchall()
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
) -> int:
    now = _now()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO schedules (
                name, target_type, target_id, action, hour, minute,
                weekdays, enabled, require_nas, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                target_type,
                target_id,
                action,
                hour,
                minute,
                weekdays,
                1 if enabled else 0,
                1 if require_nas else 0,
                now,
                now,
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
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE schedules
            SET name = ?, target_type = ?, target_id = ?, action = ?,
                hour = ?, minute = ?, weekdays = ?, enabled = ?,
                require_nas = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                name,
                target_type,
                target_id,
                action,
                hour,
                minute,
                weekdays,
                1 if enabled else 0,
                1 if require_nas else 0,
                _now(),
                schedule_id,
            ),
        )


def get_setting(key: str, default: str = "") -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default


def set_setting(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def set_settings(values: dict[str, str]) -> None:
    with get_connection() as conn:
        for key, value in values.items():
            conn.execute(
                """
                INSERT INTO app_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )


def get_nas_settings() -> dict[str, str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM app_settings WHERE key LIKE 'nas_%'").fetchall()
        settings = {row["key"]: row["value"] for row in rows}
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
    }
    defaults.update(settings)
    return defaults


def set_schedule_enabled(schedule_id: int, enabled: bool) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE schedules SET enabled = ?, updated_at = ? WHERE id = ?",
            (1 if enabled else 0, _now(), schedule_id),
        )


def delete_schedule(schedule_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))


def mark_schedule_run(schedule_id: int, error: str | None) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE schedules
            SET last_run_at = ?, last_error = ?, updated_at = ?
            WHERE id = ?
            """,
            (_now(), error, _now(), schedule_id),
        )


def create_action_run(
    source_type: str,
    source_id: str,
    target_label: str,
    action: str,
    trigger_type: str,
    schedule_id: int | None = None,
) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO action_runs (
                source_type, source_id, target_label, action, trigger_type,
                status, schedule_id, started_at
            )
            VALUES (?, ?, ?, ?, ?, 'running', ?, ?)
            """,
            (source_type, source_id, target_label, action, trigger_type, schedule_id, _now()),
        )
        return int(cursor.lastrowid)


def finish_action_run(run_id: int, status: str, error: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE action_runs
            SET status = ?, error = ?, finished_at = ?
            WHERE id = ?
            """,
            (status, error, _now(), run_id),
        )


def create_action_step(
    run_id: int,
    position: int,
    target_type: str,
    target_name: str,
    action: str,
) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO action_run_steps (
                run_id, position, target_type, target_name, action,
                status, started_at
            )
            VALUES (?, ?, ?, ?, ?, 'running', ?)
            """,
            (run_id, position, target_type, target_name, action, _now()),
        )
        return int(cursor.lastrowid)


def finish_action_step(step_id: int, status: str, message: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE action_run_steps
            SET status = ?, message = ?, finished_at = ?
            WHERE id = ?
            """,
            (status, message, _now(), step_id),
        )


def get_action_run(run_id: int) -> dict | None:
    with get_connection() as conn:
        return _row(conn.execute("SELECT * FROM action_runs WHERE id = ?", (run_id,)).fetchone())


def get_action_run_steps(run_id: int) -> list[dict]:
    with get_connection() as conn:
        return _rows(
            conn.execute(
                """
                SELECT * FROM action_run_steps
                WHERE run_id = ?
                ORDER BY position ASC, id ASC
                """,
                (run_id,),
            ).fetchall()
        )


def list_action_runs(
    source_type: str | None = None,
    source_id: str | None = None,
    schedule_id: int | None = None,
    trigger_prefix: str | None = None,
    limit: int = 20,
) -> list[dict]:
    clauses = []
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
                f"""
                SELECT * FROM action_runs
                {where}
                ORDER BY started_at DESC, id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        )
