from __future__ import annotations

import json

from app import database


def test_init_db_applies_latest_schema(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)

    database.init_db()

    with database.get_connection() as conn:
        version = conn.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()["version"]
        group_columns = {row["name"] for row in conn.execute("PRAGMA table_info(groups)").fetchall()}
        nas_tables = conn.execute(
            "SELECT COUNT(*) AS count FROM sqlite_master WHERE type='table' AND name='nas_profiles'"
        ).fetchone()["count"]

    assert version == database.SCHEMA_VERSION
    assert "conflict_policy" in group_columns
    assert "wait_for_healthy" in group_columns
    assert nas_tables == 1


def test_configuration_export_excludes_detailed_run_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    database.create_action_run("container", "abc", "example", "start", "manual")

    payload = json.loads(database.export_configuration())

    assert payload["format"] == 1
    assert "action_runs" not in payload
    assert "action_run_steps" not in payload
