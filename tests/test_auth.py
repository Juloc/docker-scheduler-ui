from app import auth


def test_form_login_is_default(monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    assert auth.get_auth_mode() == "form"


def test_invalid_auth_mode_falls_back_to_form(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "invalid")
    assert auth.get_auth_mode() == "form"
