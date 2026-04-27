import secrets
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_csrf, require_roles
from app.database import get_db
from app.models import (
    Branch,
    DeliverySession,
    DeliverySessionLine,
    DeliverySessionStatus,
    DemandLine,
    DemandStatus,
    User,
    UserRole,
)
from app.schemas import DeliveryLineInput
from app.services.delivery_service import (
    DeliveryValidationError,
    close_delivery_session,
    get_or_open_delivery_session,
    save_delivery_result,
)
from app.services.demand_service import get_active_demand_lines
from starlette.concurrency import run_in_threadpool


router = APIRouter(prefix="/driver", tags=["driver"])
templates = Jinja2Templates(directory="app/templates")
DELIVERY_FORM_TOKEN_KEY = "delivery_result_form_token"


def _drivers(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(
                User.role == UserRole.driver,
                User.is_active.is_(True),
                User.is_deleted.is_(False),
            )
            .order_by(User.full_name)
        ).all()
    )


@router.get("", response_class=HTMLResponse)
def driver_dashboard(
    request: Request,
    driver_id: int | None = None,
    q: str = "",
    show_all: bool = False,
    message: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.driver)),
):
    is_admin = current_user.role == UserRole.admin
    drivers = _drivers(db) if is_admin else [current_user]
    q = q.strip()
    selected = db.get(User, driver_id) if is_admin and driver_id else (drivers[0] if drivers else None)
    if selected and selected.role != UserRole.driver:
        selected = drivers[0] if drivers else None
    demand_summary = {
        row.branch_id: {"positions": row.positions, "qty": float(row.qty or 0)}
        for row in db.execute(
            select(
                DemandLine.branch_id,
                func.count(DemandLine.id).label("positions"),
                func.coalesce(func.sum(DemandLine.qty_remaining), 0).label("qty"),
            )
            .join(Branch)
            .where(
                DemandLine.status.in_((DemandStatus.active, DemandStatus.partially_delivered)),
                Branch.is_deleted.is_(False),
            )
            .group_by(DemandLine.branch_id)
        )
    }
    total_active_branches = len(demand_summary)
    total_active_positions = sum(row["positions"] for row in demand_summary.values())
    total_active_qty = sum(row["qty"] for row in demand_summary.values())

    branch_query = select(Branch).where(
        Branch.is_active.is_(True), Branch.is_deleted.is_(False)
    )
    if q:
        pattern = f"%{q}%"
        branch_query = branch_query.where(or_(Branch.name.ilike(pattern), Branch.address.ilike(pattern)))
    branches = list(
        db.scalars(branch_query.order_by(Branch.name)).all()
    )
    if not show_all:
        branches = [branch for branch in branches if branch.id in demand_summary]
    branches.sort(
        key=lambda branch: (
            0 if branch.id in demand_summary else 1,
            -demand_summary.get(branch.id, {"qty": 0})["qty"],
            branch.name,
        )
    )
    open_session = None
    if selected:
        open_session = db.scalar(
            select(DeliverySession)
            .where(
                DeliverySession.driver_id == selected.id,
                DeliverySession.status == DeliverySessionStatus.open,
                DeliverySession.is_deleted.is_(False),
            )
            .options(selectinload(DeliverySession.branch))
        )
    return templates.TemplateResponse(
        "driver/dashboard.html",
        {
            "request": request,
            "current_user": current_user,
            "is_admin": is_admin,
            "drivers": drivers,
            "selected": selected,
            "branches": branches,
            "demand_summary": demand_summary,
            "total_active_branches": total_active_branches,
            "total_active_positions": total_active_positions,
            "total_active_qty": total_active_qty,
            "q": q,
            "show_all": show_all,
            "open_session": open_session,
            "message": message,
            "error": error,
        },
    )


@router.get("/branch/{branch_id}", response_class=HTMLResponse)
def branch_visit(
    request: Request,
    branch_id: int,
    driver_id: int | None = None,
    session_id: int | None = None,
    message: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.driver)),
):
    is_admin = current_user.role == UserRole.admin
    branch = db.get(Branch, branch_id)
    if not branch or not branch.is_active or branch.is_deleted:
        return RedirectResponse(f"/driver?error={quote('Подразделение не найдено')}", status_code=303)
    driver = db.get(User, driver_id) if is_admin and driver_id else current_user
    if not driver or driver.role != UserRole.driver or driver.is_deleted:
        return RedirectResponse(f"/driver?error={quote('Водитель не найден')}", status_code=303)
    session = db.get(DeliverySession, session_id) if session_id else None
    if session and session.is_deleted:
        session = None
    if session and not is_admin and session.driver_id != current_user.id:
        return RedirectResponse(f"/driver?error={quote('Нет доступа к визиту')}", status_code=303)
    if not session and driver:
        session = db.scalar(
            select(DeliverySession)
            .where(
                DeliverySession.driver_id == driver.id,
                DeliverySession.branch_id == branch_id,
                DeliverySession.status == DeliverySessionStatus.open,
                DeliverySession.is_deleted.is_(False),
            )
            .order_by(DeliverySession.started_at.desc())
        )
    active_demand = get_active_demand_lines(db, branch_id)
    saved_delivery_by_demand = {}
    if session:
        saved_delivery_by_demand = {
            line.demand_line_id: line
            for line in db.scalars(
                select(DeliverySessionLine).where(
                    DeliverySessionLine.delivery_session_id == session.id
                )
            ).all()
        }
    form_token = None
    if session and session.status == DeliverySessionStatus.open:
        form_token = secrets.token_urlsafe(24)
        request.session[DELIVERY_FORM_TOKEN_KEY] = form_token
    return templates.TemplateResponse(
        "driver/visit.html",
        {
            "request": request,
            "current_user": current_user,
            "is_admin": is_admin,
            "branch": branch,
            "driver": driver,
            "session": session,
            "active_demand": active_demand,
            "saved_delivery_by_demand": saved_delivery_by_demand,
            "form_token": form_token,
            "message": message,
            "error": error,
        },
    )


@router.post("/branch/{branch_id}/open")
def open_visit(
    branch_id: int,
    driver_id: int | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.driver)),
    _: None = Depends(require_csrf),
):
    is_admin = current_user.role == UserRole.admin
    active_driver_id = int(driver_id or 0) if is_admin else current_user.id
    try:
        session = get_or_open_delivery_session(db, active_driver_id, branch_id)
    except DeliveryValidationError as exc:
        return RedirectResponse(
            f"/driver?driver_id={active_driver_id}&error={quote(str(exc))}", status_code=303
        )
    if session.branch_id != branch_id:
        return RedirectResponse(
            f"/driver?driver_id={active_driver_id}&error={quote('У водителя уже открыт визит в другое подразделение')}",
            status_code=303,
        )
    return RedirectResponse(
        f"/driver/branch/{branch_id}?driver_id={active_driver_id}&session_id={session.id}&message={quote('Визит открыт')}",
        status_code=303,
    )


@router.post("/sessions/{session_id}/save")
async def save_visit_result(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.driver)),
    _: None = Depends(require_csrf),
):
    form = await request.form()
    is_admin = current_user.role == UserRole.admin
    session = db.get(DeliverySession, session_id)
    if not session:
        return RedirectResponse(f"/driver?error={quote('Визит не найден')}", status_code=303)
    if session.is_deleted:
        return RedirectResponse(f"/driver?error={quote('Визит удалён администратором')}", status_code=303)
    if not is_admin and session.driver_id != current_user.id:
        return RedirectResponse(f"/driver?error={quote('Нет доступа к визиту')}", status_code=303)
    driver_id = session.driver_id
    branch_id = session.branch_id
    form_token = str(form.get("form_token") or "")
    session_token = request.session.pop(DELIVERY_FORM_TOKEN_KEY, None)
    if not session_token or form_token != session_token:
        return RedirectResponse(
            f"/driver/branch/{branch_id}?driver_id={driver_id}&session_id={session_id}&message={quote('Форма уже была обработана. Проверьте сохранённые строки визита.')}",
            status_code=303,
        )
    demand_line_ids = form.getlist("demand_line_id")
    qty_values = form.getlist("qty_delivered_now")
    lines = []
    for line_id_raw, qty_raw in zip(demand_line_ids, qty_values, strict=False):
        try:
            qty_value = 0 if str(qty_raw or "").strip() == "" else float(str(qty_raw).replace(",", "."))
            lines.append(DeliveryLineInput(demand_line_id=int(line_id_raw), qty_delivered_now=qty_value))
        except ValueError:
            return RedirectResponse(
                f"/driver/branch/{branch_id}?driver_id={driver_id}&session_id={session_id}&error={quote('Количество должно быть числом')}",
                status_code=303,
            )
    try:
        await run_in_threadpool(save_delivery_result, db, session_id, lines)
    except DeliveryValidationError as exc:
        return RedirectResponse(
            f"/driver/branch/{branch_id}?driver_id={driver_id}&session_id={session_id}&error={quote(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(
        f"/driver/branch/{branch_id}?driver_id={driver_id}&session_id={session_id}&message={quote('Результат доставки сохранён')}",
        status_code=303,
    )


@router.post("/sessions/{session_id}/close")
def close_visit(
    session_id: int,
    driver_id: int | None = Form(None),
    branch_id: int | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.driver)),
    _: None = Depends(require_csrf),
):
    is_admin = current_user.role == UserRole.admin
    session = db.get(DeliverySession, session_id)
    if not session:
        return RedirectResponse(f"/driver?error={quote('Визит не найден')}", status_code=303)
    if session.is_deleted:
        return RedirectResponse(f"/driver?error={quote('Визит удалён администратором')}", status_code=303)
    if not is_admin and session.driver_id != current_user.id:
        return RedirectResponse(f"/driver?error={quote('Нет доступа к визиту')}", status_code=303)
    driver_id = session.driver_id
    branch_id = session.branch_id
    try:
        close_delivery_session(db, session_id)
    except DeliveryValidationError as exc:
        return RedirectResponse(
            f"/driver/branch/{branch_id}?driver_id={driver_id}&session_id={session_id}&error={quote(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(
        f"/driver?driver_id={driver_id}&message={quote('Визит закрыт')}", status_code=303
    )
