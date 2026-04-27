from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import (
    default_path_for_role,
    get_current_user,
    hash_password,
    require_csrf,
    require_user,
    safe_next_url,
    verify_login_password,
    verify_password,
)
from app.database import get_db
from app.models import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    return templates.TemplateResponse(
        "home.html", {"request": request, "current_user": current_user}
    )


@router.get("/login", response_class=HTMLResponse)
def login_form(
    request: Request,
    next: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    if current_user:
        return RedirectResponse(
            safe_next_url(next, default_path_for_role(current_user.role)), status_code=303
        )
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "next": safe_next_url(next, "/"), "error": error},
    )


@router.post("/login")
def login(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
    _: None = Depends(require_csrf),
):
    user = db.scalar(
        select(User).where(
            User.login == login.strip(),
            User.is_active.is_(True),
            User.is_deleted.is_(False),
        )
    )
    if not user or not verify_login_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "next": safe_next_url(next, "/"),
                "error": "Неверный логин или пароль",
            },
            status_code=401,
        )

    request.session["user_id"] = user.id
    return RedirectResponse(safe_next_url(next, default_path_for_role(user.role)), status_code=303)


@router.post("/logout")
def logout(request: Request, _: None = Depends(require_csrf)):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/password", response_class=HTMLResponse)
def password_form(
    request: Request,
    message: str | None = None,
    error: str | None = None,
    current_user: User = Depends(require_user),
):
    return templates.TemplateResponse(
        "password.html",
        {
            "request": request,
            "current_user": current_user,
            "message": message,
            "error": error,
        },
    )


@router.post("/password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    new_password_confirm: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
    _: None = Depends(require_csrf),
):
    if not verify_password(current_password, current_user.password_hash):
        return templates.TemplateResponse(
            "password.html",
            {
                "request": request,
                "current_user": current_user,
                "error": "Текущий пароль указан неверно",
            },
            status_code=400,
        )
    new_password = new_password.strip()
    if len(new_password) < 8:
        return templates.TemplateResponse(
            "password.html",
            {
                "request": request,
                "current_user": current_user,
                "error": "Новый пароль должен быть не короче 8 символов",
            },
            status_code=400,
        )
    if new_password != new_password_confirm.strip():
        return templates.TemplateResponse(
            "password.html",
            {
                "request": request,
                "current_user": current_user,
                "error": "Новый пароль и подтверждение не совпадают",
            },
            status_code=400,
        )

    user = db.get(User, current_user.id)
    if not user:
        request.session.clear()
        return RedirectResponse("/login?error=Пользователь не найден", status_code=303)
    user.password_hash = hash_password(new_password)
    db.commit()
    return RedirectResponse("/password?message=Пароль изменён", status_code=303)
