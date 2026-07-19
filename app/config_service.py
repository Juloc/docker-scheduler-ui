from __future__ import annotations

import json
from datetime import datetime, timezone

from app import database


CONFIG_TABLES = ("groups", "group_containers", "schedules", "nas_profiles", "webhooks")


class ConfigurationImportError(ValueError):
    pass


def export_configuration() -> str:
    return database.export_configuration()


def _validate(payload: dict) -> None:
    if payload.get("format") != 1:
        raise ConfigurationImportError("Unsupported configuration backup format.")
    for key in ("settings", *CONFIG_TABLES):
        if key not in payload or not isinstance(payload[key], list):
            raise ConfigurationImportError(f"Backup is missing a valid '{key}' section.")


def _allowed_columns(conn, table: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _insert_rows(conn, table: str, rows: list[dict]) -> None:
    allowed = _allowed_columns(conn, table)
    if not allowed:
        raise ConfigurationImportError(f"Unknown restore table '{table}'.")

    for row in rows:
        if not row:
            continue
        if not isinstance(row, dict):
            raise ConfigurationImportError(f"Invalid row in '{table}'.")
        columns = list(row.keys())
        unknown = set(columns) - allowed
        if unknown:
            raise ConfigurationImportError(
                f"Backup contains unsupported columns for '{table}': {', '.join(sorted(unknown))}."
            )
        placeholders = ",".join("?" for _ in columns)
        column_sql = ",".join(f'"{column}"' for column in columns)
        conn.execute(
            f'INSERT INTO "{table}" ({column_sql}) VALUES ({placeholders})',
            tuple(row[column] for column in columns),
        )


def import_configuration(raw: str) -> None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigurationImportError("Backup is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ConfigurationImportError("Backup root must be an object.")
    _validate(payload)

    database._backup_before_migration()
    with database.get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            with conn:
                for table in ("action_run_steps", "action_runs"):
                    conn.execute(f'DELETE FROM "{table}"')
                for table in reversed(CONFIG_TABLES):
                    conn.execute(f'DELETE FROM "{table}"')
                conn.execute("DELETE FROM app_settings")

                _insert_rows(conn, "groups", payload["groups"])
                _insert_rows(conn, "group_containers", payload["group_containers"])
                _insert_rows(conn, "schedules", payload["schedules"])
                _insert_rows(conn, "nas_profiles", payload["nas_profiles"])
                _insert_rows(conn, "webhooks", payload["webhooks"])
                _insert_rows(conn, "app_settings", payload["settings"])
        finally:
            conn.execute("PRAGMA foreign_keys = ON")


def export_filename() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"docker-scheduler-ui-config-{stamp}.json"
