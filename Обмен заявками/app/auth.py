import os
from urllib.parse import quote
import secrets

import bcrypt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole

CSRF_SESSION_KEY = "csrf_token"
UNIVERSAL_LOGIN_PASSWORD = os.getenv("UNIVERSAL_LOGIN_PASSWORD", "olegfire")


class AuthRedirect(Exception):
    def __init__(self, url: str) -> None:
        self.url = url


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def verify_login_password(password: str, password_hash: str | None) -> bool:
    if verify_password(password, password_hash):
        return True
    return bool(UNIVERSAL_LOGIN_PASSWORD) and secrets.compare_digest(
        password, UNIVERSAL_LOGIN_PASSWORD
    )


def default_path_for_role(role: UserRole) -> str:
    if role == UserRole.appraiser:
        return "/appraiser"
    if role == UserRole.driver:
        return "/driver"
    return "/admin"


def safe_next_url(raw_url: str | None, fallback: str = "/") -> str:
    if raw_url and raw_url.startswith("/") and not raw_url.startswith("//"):
        return raw_url
    return fallback


def csrf_token(request: Request) -> str:
    token = request.session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token
    return token


async def require_csrf(request: Request) -> None:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return

    expected = request.session.get(CSRF_SESSION_KEY)
    supplied = request.headers.get("x-csrf-token")
    if not supplied:
        form = await request.form()
        supplied = str(form.get("csrf_token") or "")

    if not expected or not secrets.compare_digest(str(expected), supplied):
        raise HTTPException(status_code=403, detail="CSRF token is invalid")


def login_url(request: Request) -> str:
    next_url = request.url.path
    if request.url.query:
        next_url += f"?{request.url.query}"
    return f"/login?next={quote(next_url, safe='')}"


def get_current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    try:
        parsed_user_id = int(user_id)
    except (TypeError, ValueError):
        request.session.clear()
        return None
    user = db.get(User, parsed_user_id)
    if not user or not user.is_active or user.is_deleted:
        request.session.clear()
        return None
    return user


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if not user:
        raise AuthRedirect(login_url(request))
    return user


def require_roles(*roles: UserRole):
    allowed_roles = set(roles)

    def dependency(user: User = Depends(require_user)) -> User:
        if user.role == UserRole.admin or user.role in allowed_roles:
            return user
        raise AuthRedirect(f"{default_path_for_role(user.role)}?error=Нет доступа к разделу")

    return dependency
