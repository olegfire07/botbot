import secrets
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_csrf, require_roles
from app.database import get_db
from app.models import Branch, Item, Request as GoodsRequest, RequestLine, User, UserRole
from app.schemas import RequestLineInput
from app.services.demand_service import get_active_demand_lines
from app.services.request_service import RequestValidationError, create_request
from app.services.websocket_service import manager
import asyncio
from starlette.concurrency import run_in_threadpool


router = APIRouter(prefix="/appraiser", tags=["appraiser"])
templates = Jinja2Templates(directory="app/templates")
REQUEST_FORM_TOKEN_KEY = "appraiser_request_form_token"


def _appraisers(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(
                User.role == UserRole.appraiser,
                User.is_active.is_(True),
                User.is_deleted.is_(False),
            )
            .options(selectinload(User.branch))
            .order_by(User.full_name)
        ).all()
    )


@router.get("", response_class=HTMLResponse)
def appraiser_dashboard(
    request: Request,
    user_id: int | None = None,
    branch_id: int | None = None,
    branch_q: str = "",
    search_mode: str = "select",
    message: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.appraiser)),
):
    is_admin = current_user.role == UserRole.admin
    appraisers = _appraisers(db) if is_admin else [current_user]
    selected = None
    if is_admin:
        selected = db.get(User, user_id) if user_id else (appraisers[0] if appraisers else None)
        if selected and selected.role != UserRole.appraiser:
            selected = appraisers[0] if appraisers else None
    else:
        selected = current_user

    branch_q = branch_q.strip() if is_admin else ""
    if is_admin:
        branch_query = select(Branch).where(
            Branch.is_active.is_(True), Branch.is_deleted.is_(False)
        )
        if branch_q:
            pattern = f"%{branch_q}%"
            branch_query = branch_query.where(
                or_(Branch.name.ilike(pattern), Branch.address.ilike(pattern))
            )
        branches = list(db.scalars(branch_query.order_by(Branch.name)).all())
        if search_mode == "search" and branch_q:
            selected_branch_id = branches[0].id if branches else None
        else:
            selected_branch_id = branch_id or (selected.branch_id if selected else None)
    else:
        selected_branch_id = selected.branch_id if selected else None
        selected_branch_for_list = db.get(Branch, selected_branch_id) if selected_branch_id else None
        if selected_branch_for_list and selected_branch_for_list.is_deleted:
            selected_branch_for_list = None
        branches = [selected_branch_for_list] if selected_branch_for_list else []

    selected_branch = db.get(Branch, selected_branch_id) if selected_branch_id else None
    if selected_branch and selected_branch.is_deleted:
        selected_branch = None
        selected_branch_id = None
    if (
        is_admin
        and selected_branch
        and selected_branch.id not in {branch.id for branch in branches}
        and search_mode != "search"
    ):
        branches.insert(0, selected_branch)
    active_demand = get_active_demand_lines(db, selected_branch_id) if selected_branch_id else []
    requests = []
    if selected:
        requests = list(
            db.scalars(
                select(GoodsRequest)
                .where(
                    GoodsRequest.created_by_user_id == selected.id,
                    GoodsRequest.branch_id == selected_branch_id,
                    GoodsRequest.is_deleted.is_(False),
                )
                .options(
                    selectinload(GoodsRequest.branch),
                    selectinload(GoodsRequest.lines).selectinload(RequestLine.item),
                )
                .order_by(GoodsRequest.created_at.desc())
            ).all()
        )
    return templates.TemplateResponse(
        "appraiser/dashboard.html",
        {
            "request": request,
            "current_user": current_user,
            "is_admin": is_admin,
            "appraisers": appraisers,
            "branches": branches,
            "branch_results_count": len(branches),
            "branch_q": branch_q,
            "search_mode": search_mode,
            "selected": selected,
            "selected_branch": selected_branch,
            "active_demand": active_demand,
            "requests": requests,
            "message": message,
            "error": error,
        },
    )


@router.get("/requests/new", response_class=HTMLResponse)
def new_request_form(
    request: Request,
    user_id: int | None = None,
    branch_id: int | None = None,
    branch_q: str = "",
    search_mode: str = "select",
    error: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.appraiser)),
):
    form_token = secrets.token_urlsafe(24)
    request.session[REQUEST_FORM_TOKEN_KEY] = form_token
    is_admin = current_user.role == UserRole.admin
    if is_admin:
        appraisers = _appraisers(db)
        appraiser = db.get(User, user_id) if user_id else (appraisers[0] if appraisers else None)
        if appraiser and appraiser.role != UserRole.appraiser:
            appraiser = appraisers[0] if appraisers else None
        branch_q = branch_q.strip()
        branch_query = select(Branch).where(
            Branch.is_active.is_(True), Branch.is_deleted.is_(False)
        )
        if branch_q:
            pattern = f"%{branch_q}%"
            branch_query = branch_query.where(
                or_(Branch.name.ilike(pattern), Branch.address.ilike(pattern))
            )
        branches = list(db.scalars(branch_query.order_by(Branch.name)).all())
        if search_mode == "search" and branch_q:
            selected_branch_id = branches[0].id if branches else None
        else:
            selected_branch_id = branch_id or (appraiser.branch_id if appraiser else None)
    else:
        appraiser = current_user
        branch_q = ""
        selected_branch_id = appraiser.branch_id
        selected_branch_for_list = db.get(Branch, selected_branch_id) if selected_branch_id else None
        if selected_branch_for_list and selected_branch_for_list.is_deleted:
            selected_branch_for_list = None
        branches = [selected_branch_for_list] if selected_branch_for_list else []
    selected_branch = db.get(Branch, selected_branch_id) if selected_branch_id else None
    if selected_branch and selected_branch.is_deleted:
        selected_branch = None
        selected_branch_id = None
    if (
        is_admin
        and selected_branch
        and selected_branch.id not in {branch.id for branch in branches}
        and search_mode != "search"
    ):
        branches.insert(0, selected_branch)
    items = list(
        db.scalars(
            select(Item)
            .where(Item.is_active.is_(True), Item.is_deleted.is_(False))
            .order_by(Item.name)
        ).all()
    )
    return templates.TemplateResponse(
        "appraiser/new_request.html",
        {
            "request": request,
            "current_user": current_user,
            "is_admin": is_admin,
            "appraiser": appraiser,
            "branches": branches,
            "branch_results_count": len(branches),
            "selected_branch_id": selected_branch_id,
            "branch_q": branch_q,
            "search_mode": search_mode,
            "items": items,
            "form_token": form_token,
            "error": error,
        },
    )


@router.post("/requests", response_class=HTMLResponse)
async def submit_request(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.appraiser)),
    _: None = Depends(require_csrf),
):
    form = await request.form()
    is_admin = current_user.role == UserRole.admin
    user_id = int(form.get("user_id") or 0) if is_admin else current_user.id
    branch_id = int(form.get("branch_id") or 0) if is_admin else int(current_user.branch_id or 0)
    comment = str(form.get("comment") or "").strip() or None
    form_token = str(form.get("form_token") or "")
    session_token = request.session.pop(REQUEST_FORM_TOKEN_KEY, None)
    if not session_token or form_token != session_token:
        return RedirectResponse(
            f"/appraiser?user_id={user_id}&branch_id={branch_id}&message={quote('Форма уже была обработана. Проверьте историю заявок.')}",
            status_code=303,
        )
    item_ids = form.getlist("item_id")
    quantities = form.getlist("qty_requested")
    comments = form.getlist("line_comment")

    lines: list[RequestLineInput] = []
    for item_id_raw, qty_raw, comment_raw in zip(item_ids, quantities, comments, strict=False):
        if not item_id_raw and not qty_raw:
            continue
        try:
            item_id = int(item_id_raw or 0)
            qty = float(str(qty_raw or "0").replace(",", "."))
        except ValueError:
            return RedirectResponse(
                f"/appraiser/requests/new?user_id={user_id}&branch_id={branch_id}&error={quote('Количество должно быть числом')}",
                status_code=303,
            )
        lines.append(
            RequestLineInput(
                item_id=item_id,
                qty_requested=qty,
                comment=str(comment_raw or "").strip() or None,
            )
        )

    try:
        await run_in_threadpool(create_request, db, user_id, branch_id, comment, lines)
        branch = await run_in_threadpool(db.get, Branch, branch_id)
        if branch:
            asyncio.create_task(manager.broadcast_to_roles(
                ["driver", "admin"], 
                {"type": "new_request", "branch_id": branch.id, "message": f"Новая заявка: {branch.name}"}
            ))
    except RequestValidationError as exc:
        return RedirectResponse(
            f"/appraiser/requests/new?user_id={user_id}&branch_id={branch_id}&error={quote(str(exc))}",
            status_code=303,
        )

    return RedirectResponse(
        f"/appraiser?user_id={user_id}&branch_id={branch_id}&message={quote('Заявка сохранена, активная потребность обновлена')}",
        status_code=303,
    )
