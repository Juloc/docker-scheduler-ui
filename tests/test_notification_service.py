from pathlib import Path

from app import database, notification_service


def test_webhook_event_filter_and_payload(monkeypatch, tmp_path: Path):
    database.DB_PATH = tmp_path / "app.db"
    database.init_db()
    notification_service.save_webhook(
        None,
        "Discord alerts",
        "discord",
        "https://example.invalid/hook",
        True,
        ["run_failed"],
    )
    delivered = []
    monkeypatch.setattr(notification_service, "_post", lambda url, payload: delivered.append((url, payload)))

    notification_service.send_event("nas_online", "NAS online", "ready")
    assert delivered == []

    errors = notification_service.send_event("run_failed", "Run failed", "boom", {"run_id": 7})
    assert errors == []
    assert delivered == [
        ("https://example.invalid/hook", {"content": "**Run failed**\nboom"})
    ]


def test_test_webhook_uses_selected_webhook(monkeypatch, tmp_path: Path):
    database.DB_PATH = tmp_path / "app.db"
    database.init_db()
    webhook_id = notification_service.save_webhook(
        None,
        "Generic",
        "generic",
        "https://example.invalid/test",
        True,
        [],
    )
    delivered = []
    monkeypatch.setattr(notification_service, "_post", lambda url, payload: delivered.append((url, payload)))

    notification_service.test_webhook(webhook_id)

    assert delivered[0][0] == "https://example.invalid/test"
    assert delivered[0][1]["event"] == "test"
