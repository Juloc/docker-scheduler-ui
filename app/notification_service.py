from __future__ import annotations

import json
import urllib.error
import urllib.request

from app import database


DEFAULT_TIMEOUT_SECONDS = 5
DEFAULT_RETRIES = 2


def list_webhooks() -> list[dict]:
    with database.get_connection() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM webhooks ORDER BY name, id").fetchall()]


def save_webhook(webhook_id: int | None, name: str, kind: str, url: str, enabled: bool, events: list[str]) -> int:
    kind = kind if kind in {"generic", "discord", "home_assistant"} else "generic"
    now = database._now()
    event_value = ",".join(sorted(set(event for event in events if event)))
    with database.get_connection() as conn:
        if webhook_id is None:
            cursor = conn.execute(
                "INSERT INTO webhooks (name, kind, url, enabled, events, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name.strip() or "Webhook", kind, url.strip(), 1 if enabled else 0, event_value, now, now),
            )
            return int(cursor.lastrowid)
        conn.execute(
            "UPDATE webhooks SET name=?, kind=?, url=?, enabled=?, events=?, updated_at=? WHERE id=?",
            (name.strip() or "Webhook", kind, url.strip(), 1 if enabled else 0, event_value, now, webhook_id),
        )
        return webhook_id


def delete_webhook(webhook_id: int) -> None:
    with database.get_connection() as conn:
        conn.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))


def _payload(kind: str, event: str, title: str, message: str, details: dict | None) -> dict:
    details = details or {}
    if kind == "discord":
        return {"content": f"**{title}**\n{message}"}
    if kind == "home_assistant":
        return {"event": event, "title": title, "message": message, "details": details}
    return {"event": event, "title": title, "message": message, "details": details}


def _post(url: str, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "docker-scheduler-ui"},
    )
    last_error: Exception | None = None
    for _ in range(DEFAULT_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
                if response.status >= 400:
                    raise RuntimeError(f"Webhook returned HTTP {response.status}.")
                return
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            last_error = exc
    raise RuntimeError(f"Webhook delivery failed: {last_error}")


def send_event(event: str, title: str, message: str, details: dict | None = None) -> list[str]:
    errors: list[str] = []
    for webhook in list_webhooks():
        if not webhook.get("enabled"):
            continue
        events = {value for value in str(webhook.get("events") or "").split(",") if value}
        if events and event not in events:
            continue
        try:
            _post(webhook["url"], _payload(webhook["kind"], event, title, message, details))
        except Exception as exc:
            errors.append(f"{webhook['name']}: {exc}")
    return errors


def test_webhook(webhook_id: int) -> None:
    webhook = next((item for item in list_webhooks() if item["id"] == webhook_id), None)
    if not webhook:
        raise ValueError("Webhook was not found.")
    _post(
        webhook["url"],
        _payload(webhook["kind"], "test", "docker-scheduler-ui test", "Webhook configuration is working.", {}),
    )
