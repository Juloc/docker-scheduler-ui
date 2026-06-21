import base64
import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import RedirectResponse, Response


SESSION_COOKIE = "docker_scheduler_session"


def get_auth_mode() -> str:
    mode = os.getenv("AUTH_MODE", "basic").strip().lower()
    return mode if mode in {"basic", "form"} else "basic"


def _credentials() -> tuple[str, str]:
    return os.getenv("APP_USER", "admin"), os.getenv("APP_PASSWORD", "change-me")


def verify_credentials(username: str, password: str) -> bool:
    expected_user, expected_password = _credentials()
    return secrets.compare_digest(username, expected_user) and secrets.compare_digest(password, expected_password)


def _secret() -> bytes:
    secret = os.getenv("APP_SECRET") or os.getenv("APP_PASSWORD", "change-me")
    return secret.encode("utf-8")


def _session_max_age() -> int:
    try:
        return int(os.getenv("AUTH_SESSION_SECONDS", "43200"))
    except ValueError:
        return 43200


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def create_session_token(username: str) -> str:
    issued_at = str(int(time.time()))
    payload = f"{username}:{issued_at}"
    return f"{payload}:{_sign(payload)}"


def verify_session_token(token: str | None) -> str | None:
    if not token:
        return None

    parts = token.split(":")
    if len(parts) != 3:
        return None

    username, issued_at, signature = parts
    payload = f"{username}:{issued_at}"
    if not secrets.compare_digest(signature, _sign(payload)):
        return None

    try:
        age = int(time.time()) - int(issued_at)
    except ValueError:
        return None

    if age < 0 or age > _session_max_age():
        return None
    return username


def authenticate_basic_header(header_value: str | None) -> str | None:
    if not header_value or not header_value.lower().startswith("basic "):
        return None
    encoded = header_value.split(" ", 1)[1].strip()
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
        username, password = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        return None
    return username if verify_credentials(username, password) else None


def authenticated_user(request: Request) -> str | None:
    if get_auth_mode() == "form":
        return verify_session_token(request.cookies.get(SESSION_COOKIE))
    return authenticate_basic_header(request.headers.get("authorization"))


def auth_failed_response(request: Request) -> Response:
    if get_auth_mode() == "form":
        next_path = request.url.path
        if request.url.query:
            next_path = f"{next_path}?{request.url.query}"
        return RedirectResponse(f"/login?next={quote(next_path, safe='')}", status_code=303)

    return Response(
        "Authentication required",
        status_code=401,
        headers={"WWW-Authenticate": "Basic"},
    )


def set_session_cookie(response: Response, username: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(username),
        max_age=_session_max_age(),
        httponly=True,
        samesite="lax",
        secure=os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)
