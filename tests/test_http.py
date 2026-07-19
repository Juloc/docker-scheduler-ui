from pathlib import Path

from fastapi.testclient import TestClient

from app import database
from app.main import app


def _client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("AUTH_MODE", "form")
    monkeypatch.setenv("APP_USER", "admin")
    monkeypatch.setenv("APP_PASSWORD", "secret")
    monkeypatch.setenv("APP_SECRET", "test-secret")
    database.DB_PATH = tmp_path / "app.db"
    return TestClient(app)


def _login(client: TestClient, next_path: str = "/"):
    return client.post(
        "/login",
        data={"username": "admin", "password": "secret", "next": next_path},
        follow_redirects=False,
    )


def test_unauthenticated_request_redirects_to_login(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        response = client.get("/settings", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?next=")


def test_form_login_and_settings_autosave_endpoint(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        login = _login(client, "/settings")
        assert login.status_code == 303
        assert login.headers["location"] == "/settings"

        saved = client.post(
            "/settings/preferences",
            data={"log_retention_days": "45"},
            headers={"Origin": "http://testserver"},
        )

    assert saved.status_code == 200
    assert database.get_setting("log_retention_days") == "45"


def test_cross_origin_state_change_is_rejected(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        _login(client)
        response = client.post(
            "/settings/preferences",
            data={"log_retention_days": "60"},
            headers={"Origin": "https://attacker.example"},
        )

    assert response.status_code == 403
    assert database.get_setting("log_retention_days") != "60"


def test_authenticated_container_workspace_is_available_without_docker(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        _login(client, "/containers")
        response = client.get("/containers")

    assert response.status_code == 200
    assert "Containers" in response.text
    assert "Group by Compose project" in response.text
    assert "Hide infrastructure" in response.text


def test_all_primary_workspaces_are_reachable_after_route_extraction(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        _login(client)
        for path in ("/", "/containers", "/groups", "/schedules", "/nas", "/logs", "/settings"):
            response = client.get(path)
            assert response.status_code == 200, path
