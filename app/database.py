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
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS group_containers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                container_id TEXT NOT NULL,
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
                last_run_at TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
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
    containers: list[tuple[str, int]],
) -> None:
    conn.execute("DELETE FROM group_containers WHERE group_id = ?", (group_id,))
    for index, (container_id, position) in enumerate(containers, start=1):
        conn.execute(
            """
            INSERT INTO group_containers (group_id, container_id, position)
            VALUES (?, ?, ?)
            """,
            (group_id, container_id, position or index),
        )


def create_group(name: str, delay_seconds: int, containers: list[tuple[str, int]]) -> int:
    now = _now()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO groups (name, delay_seconds, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, delay_seconds, now, now),
        )
        group_id = int(cursor.lastrowid)
        _replace_group_containers(conn, group_id, containers)
        return group_id


def update_group(
    group_id: int,
    name: str,
    delay_seconds: int,
    containers: list[tuple[str, int]],
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE groups
            SET name = ?, delay_seconds = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, delay_seconds, _now(), group_id),
        )
        _replace_group_containers(conn, group_id, containers)


def delete_group(group_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        conn.execute(
            "DELETE FROM schedules WHERE target_type = 'group' AND target_id = ?",
            (str(group_id),),
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
) -> int:
    now = _now()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO schedules (
                name, target_type, target_id, action, hour, minute,
                weekdays, enabled, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE schedules
            SET name = ?, target_type = ?, target_id = ?, action = ?,
                hour = ?, minute = ?, weekdays = ?, enabled = ?,
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
                _now(),
                schedule_id,
            ),
        )


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
