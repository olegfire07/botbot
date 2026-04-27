import csv
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from app.auth import hash_password, require_csrf, require_roles
from app.database import DATABASE_PATH, DATABASE_URL, get_db
from app.models import (
    AuditLog,
    Branch,
    DeliveryResultStatus,
    DeliverySession,
    DeliverySessionLine,
    DeliverySessionStatus,
    DemandLine,
    DemandStatus,
    Item,
    Request as GoodsRequest,
    RequestLine,
    RequestStatus,
    User,
    UserRole,
    utc_now,
)
from app.services.demand_service import ACTIVE_DEMAND_STATUSES, recalculate_demand_status
from app.services.excel_service import (
    build_deliveries_xlsx,
    build_demand_xlsx,
    build_requests_xlsx,
    build_summary_xlsx,
)
from starlette.concurrency import run_in_threadpool


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_roles(UserRole.admin)), Depends(require_csrf)],
)
templates = Jinja2Templates(directory="app/templates")


def _money(value: object) -> float:
    return round(float(value or 0), 2)


def _parse_date(raw: str | None, default: datetime | None = None) -> datetime | None:
    if not raw:
        return default
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d")
    except ValueError:
        return default


def _csv_response(filename: str, rows: list[dict[str, object]]) -> StreamingResponse:
    output = StringIO()
    fieldnames = list(rows[0].keys()) if rows else ["empty"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv; charset=utf-8", headers=headers)


def _xlsx_response(filename: str, buf: BytesIO) -> StreamingResponse:
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


def _active_admins(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User).where(
                User.role == UserRole.admin,
                User.is_active.is_(True),
                User.is_deleted.is_(False),
            )
        ).all()
    )


def _super_admin_error(current_user: User) -> RedirectResponse | None:
    if current_user.is_super_admin:
        return None
    return RedirectResponse(
        f"/admin?error={quote('Действие доступно только суперадмину')}#super",
        status_code=303,
    )


def _audit(
    db: Session,
    actor: User,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    details: str | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        )
    )


def _parse_decimal(raw: object, field_name: str) -> Decimal:
    try:
        value = Decimal(str(raw or "0").replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"{field_name} должно быть числом.") from None
    if value <= 0:
        raise ValueError(f"{field_name} должно быть больше 0.")
    return value


def _parse_non_negative_decimal(raw: object, field_name: str) -> Decimal:
    try:
        value = Decimal(str(raw or "0").replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"{field_name} должно быть числом.") from None
    if value < 0:
        raise ValueError(f"{field_name} не может быть меньше 0.")
    return value


def _request_has_delivery(db: Session, request: GoodsRequest) -> bool:
    item_ids = [line.item_id for line in request.lines]
    if not item_ids:
        return False
    return (
        db.scalar(
            select(DeliverySessionLine.id)
            .join(DeliverySession)
            .where(
                DeliverySession.branch_id == request.branch_id,
                DeliverySessionLine.item_id.in_(item_ids),
                DeliverySession.is_deleted.is_(False),
            )
            .limit(1)
        )
        is not None
    )


def _adjust_active_demand(
    db: Session, branch_id: int, item_id: int, qty_delta: Decimal
) -> None:
    if qty_delta == 0:
        return
    demand_line = db.scalar(
        select(DemandLine)
        .where(
            DemandLine.branch_id == branch_id,
            DemandLine.item_id == item_id,
            DemandLine.status.in_(ACTIVE_DEMAND_STATUSES),
        )
        .with_for_update()
    )
    if not demand_line:
        if qty_delta < 0:
            raise ValueError("Активная потребность для корректировки не найдена.")
        demand_line = DemandLine(
            branch_id=branch_id,
            item_id=item_id,
            qty_total_requested=qty_delta,
            qty_total_delivered=0,
            qty_remaining=qty_delta,
            status=DemandStatus.active,
        )
        db.add(demand_line)
        return

    demand_line.qty_total_requested = Decimal(demand_line.qty_total_requested) + qty_delta
    demand_line.qty_remaining = Decimal(demand_line.qty_remaining) + qty_delta
    if Decimal(demand_line.qty_total_requested) <= 0:
        db.delete(demand_line)
        return
    if Decimal(demand_line.qty_remaining) < 0:
        raise ValueError("Нельзя уменьшить заявку ниже уже доставленного количества.")
    recalculate_demand_status(demand_line)


def _cancel_demand_lines(
    db: Session,
    actor: User,
    *,
    branch_id: int | None = None,
    item_id: int | None = None,
    reason: str,
) -> int:
    query = select(DemandLine).where(
        DemandLine.status.in_((DemandStatus.active, DemandStatus.partially_delivered))
    )
    if branch_id is not None:
        query = query.where(DemandLine.branch_id == branch_id)
    if item_id is not None:
        query = query.where(DemandLine.item_id == item_id)
    lines = list(db.scalars(query).all())
    for line in lines:
        line.qty_remaining = 0
        line.status = DemandStatus.cancelled
        line.last_updated_at = utc_now()
        _audit(db, actor, "cancel", "demand_line", line.id, reason)
    return len(lines)


def _result_status(qty_delivered: Decimal, qty_after: Decimal) -> DeliveryResultStatus:
    if qty_delivered == 0:
        return DeliveryResultStatus.none
    if qty_after > 0:
        return DeliveryResultStatus.partial
    return DeliveryResultStatus.full


def _recalculate_all_demand(db: Session) -> None:
    requested_rows = db.execute(
        select(
            GoodsRequest.branch_id,
            RequestLine.item_id,
            func.coalesce(func.sum(RequestLine.qty_requested), 0).label("qty"),
        )
        .select_from(RequestLine)
        .join(GoodsRequest)
        .join(Branch, Branch.id == GoodsRequest.branch_id)
        .join(Item, Item.id == RequestLine.item_id)
        .where(
            GoodsRequest.is_deleted.is_(False),
            Branch.is_deleted.is_(False),
            Item.is_deleted.is_(False),
        )
        .group_by(GoodsRequest.branch_id, RequestLine.item_id)
    ).all()
    delivered_rows = db.execute(
        select(
            DeliverySession.branch_id,
            DeliverySessionLine.item_id,
            func.coalesce(func.sum(DeliverySessionLine.qty_delivered_now), 0).label("qty"),
        )
        .select_from(DeliverySessionLine)
        .join(DeliverySession)
        .join(Branch, Branch.id == DeliverySession.branch_id)
        .join(Item, Item.id == DeliverySessionLine.item_id)
        .where(
            DeliverySession.is_deleted.is_(False),
            Branch.is_deleted.is_(False),
            Item.is_deleted.is_(False),
        )
        .group_by(DeliverySession.branch_id, DeliverySessionLine.item_id)
    ).all()
    requested = {
        (row.branch_id, row.item_id): Decimal(row.qty or 0) for row in requested_rows
    }
    delivered = {
        (row.branch_id, row.item_id): Decimal(row.qty or 0) for row in delivered_rows
    }
    all_keys = set(requested) | set(delivered)
    existing = {
        (line.branch_id, line.item_id): line for line in db.scalars(select(DemandLine)).all()
    }

    for key, demand_line in existing.items():
        if key not in all_keys:
            demand_line.qty_total_requested = 0
            demand_line.qty_total_delivered = 0
            demand_line.qty_remaining = 0
            demand_line.status = DemandStatus.delivered
            demand_line.last_updated_at = utc_now()

    for branch_id, item_id in all_keys:
        requested_qty = requested.get((branch_id, item_id), Decimal("0"))
        delivered_qty = delivered.get((branch_id, item_id), Decimal("0"))
        total_requested = max(requested_qty, delivered_qty)
        demand_line = existing.get((branch_id, item_id))
        if not demand_line:
            demand_line = DemandLine(
                branch_id=branch_id,
                item_id=item_id,
                qty_total_requested=total_requested,
                qty_total_delivered=delivered_qty,
                qty_remaining=total_requested - delivered_qty,
                status=DemandStatus.active,
            )
            db.add(demand_line)
        else:
            demand_line.qty_total_requested = total_requested
            demand_line.qty_total_delivered = delivered_qty
            demand_line.qty_remaining = total_requested - delivered_qty
        recalculate_demand_status(demand_line)


def _analytics(db: Session, date_from: datetime | None = None, date_to: datetime | None = None) -> dict[str, object]:
    active_cond = DemandLine.status.in_((DemandStatus.active, DemandStatus.partially_delivered))
    active_res = db.execute(
        select(
            func.count(DemandLine.id),
            func.coalesce(func.sum(DemandLine.qty_remaining), 0),
            func.coalesce(func.sum(DemandLine.qty_remaining * Item.unit_cost), 0)
        )
        .select_from(DemandLine)
        .join(Item)
        .join(Branch)
        .where(active_cond, Item.is_deleted.is_(False), Branch.is_deleted.is_(False))
    ).first()
    active_positions, active_qty, active_cost = active_res or (0, 0, 0)

    req_query = select(
        func.coalesce(func.sum(RequestLine.qty_requested), 0),
        func.coalesce(func.sum(RequestLine.qty_requested * Item.unit_cost), 0)
    ).select_from(RequestLine).join(Item).join(GoodsRequest).join(
        Branch, Branch.id == GoodsRequest.branch_id
    ).where(
        GoodsRequest.is_deleted.is_(False),
        Item.is_deleted.is_(False),
        Branch.is_deleted.is_(False),
    )
    
    if date_from:
        req_query = req_query.where(GoodsRequest.created_at >= date_from)
    if date_to:
        req_query = req_query.where(GoodsRequest.created_at < date_to + timedelta(days=1))
        
    requested_qty, requested_cost = db.execute(req_query).first() or (0, 0)

    del_query = select(
        func.coalesce(func.sum(DeliverySessionLine.qty_delivered_now), 0),
        func.coalesce(func.sum(DeliverySessionLine.qty_delivered_now * Item.unit_cost), 0)
    ).select_from(DeliverySessionLine).join(Item).join(DeliverySession).join(
        Branch, Branch.id == DeliverySession.branch_id
    ).where(
        DeliverySession.is_deleted.is_(False),
        Item.is_deleted.is_(False),
        Branch.is_deleted.is_(False),
    )
    
    sess_query = select(func.count(DeliverySession.id)).where(DeliverySession.is_deleted.is_(False))
    
    if date_from:
        del_query = del_query.where(DeliverySession.started_at >= date_from)
        sess_query = sess_query.where(DeliverySession.started_at >= date_from)
    if date_to:
        del_query = del_query.where(DeliverySession.started_at < date_to + timedelta(days=1))
        sess_query = sess_query.where(DeliverySession.started_at < date_to + timedelta(days=1))
        
    delivered_qty, delivered_cost = db.execute(del_query).first() or (0, 0)
    delivery_sessions_count = db.scalar(sess_query) or 0

    branch_rows_res = db.execute(
        select(
            Branch,
            func.count(DemandLine.id).label("positions"),
            func.sum(DemandLine.qty_remaining).label("qty"),
            func.sum(DemandLine.qty_remaining * Item.unit_cost).label("cost")
        ).select_from(DemandLine)
        .join(Branch)
        .join(Item)
        .where(active_cond, Branch.is_deleted.is_(False), Item.is_deleted.is_(False))
        .group_by(Branch.id)
        .order_by(text("cost DESC"), text("qty DESC"))
        .limit(10)
    ).all()
    
    branch_rows = []
    max_branch_cost = 1
    if branch_rows_res:
        max_branch_cost = max(1, float(branch_rows_res[0].cost or 0))
    for row in branch_rows_res:
        branch_rows.append({
            "branch": row.Branch,
            "positions": row.positions,
            "qty": float(row.qty or 0),
            "cost": float(row.cost or 0),
            "percent": int((float(row.cost or 0) / max_branch_cost) * 100) if max_branch_cost else 0
        })

    item_rows_res = db.execute(
        select(
            Item,
            func.count(func.distinct(DemandLine.branch_id)).label("branches_count"),
            func.sum(DemandLine.qty_remaining).label("qty"),
            func.sum(DemandLine.qty_remaining * Item.unit_cost).label("cost")
        ).select_from(DemandLine)
        .join(Item)
        .where(active_cond, Item.is_deleted.is_(False))
        .group_by(Item.id)
        .order_by(text("cost DESC"), text("qty DESC"))
        .limit(10)
    ).all()

    item_rows = []
    max_item_cost = 1
    if item_rows_res:
        max_item_cost = max(1, float(item_rows_res[0].cost or 0))
    for row in item_rows_res:
        item_rows.append({
            "item": row.Item,
            "branches_count": row.branches_count,
            "qty": float(row.qty or 0),
            "cost": float(row.cost or 0),
            "percent": int((float(row.cost or 0) / max_item_cost) * 100) if max_item_cost else 0
        })

    active_branches = (
        db.scalar(
            select(func.count(func.distinct(DemandLine.branch_id)))
            .select_from(DemandLine)
            .join(Branch)
            .where(active_cond, Branch.is_deleted.is_(False))
        )
        or 0
    )

    return {
        "active_positions": active_positions,
        "active_branches": active_branches,
        "active_qty": float(active_qty),
        "active_cost": float(active_cost),
        "requested_qty": float(requested_qty),
        "requested_cost": float(requested_cost),
        "delivered_qty": float(delivered_qty),
        "delivered_cost": float(delivered_cost),
        "delivery_sessions_count": delivery_sessions_count,
        "branch_rows": branch_rows,
        "item_rows": item_rows,
    }


@router.get("", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    message: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    branches = list(
        db.scalars(select(Branch).where(Branch.is_deleted.is_(False)).order_by(Branch.name)).all()
    )
    users = list(
        db.scalars(
            select(User)
            .where(User.is_deleted.is_(False))
            .options(selectinload(User.branch))
            .order_by(User.full_name)
        ).all()
    )
    items = list(
        db.scalars(select(Item).where(Item.is_deleted.is_(False)).order_by(Item.name)).all()
    )
    requests = list(
        db.scalars(
            select(GoodsRequest)
            .where(GoodsRequest.is_deleted.is_(False))
            .options(
                selectinload(GoodsRequest.branch),
                selectinload(GoodsRequest.created_by),
                selectinload(GoodsRequest.lines).selectinload(RequestLine.item),
            )
            .order_by(GoodsRequest.created_at.desc())
            .limit(50)
        ).all()
    )
    demand_lines = list(
        db.scalars(
            select(DemandLine)
            .join(Branch)
            .join(Item)
            .where(DemandLine.status.in_((DemandStatus.active, DemandStatus.partially_delivered)))
            .options(selectinload(DemandLine.branch), selectinload(DemandLine.item))
            .where(Branch.is_deleted.is_(False), Item.is_deleted.is_(False))
            .order_by(DemandLine.last_updated_at.desc())
            .limit(50)
        ).all()
    )
    sessions = list(
        db.scalars(
            select(DeliverySession)
            .where(DeliverySession.is_deleted.is_(False))
            .options(
                selectinload(DeliverySession.branch),
                selectinload(DeliverySession.driver),
                selectinload(DeliverySession.lines).selectinload(DeliverySessionLine.item),
            )
            .order_by(DeliverySession.started_at.desc())
            .limit(50)
        ).all()
    )
    deleted_requests = []
    deleted_sessions = []
    audit_logs = []
    if current_user.is_super_admin:
        deleted_requests = list(
            db.scalars(
                select(GoodsRequest)
                .where(GoodsRequest.is_deleted.is_(True))
                .options(
                    selectinload(GoodsRequest.branch),
                    selectinload(GoodsRequest.created_by),
                    selectinload(GoodsRequest.lines).selectinload(RequestLine.item),
                )
                .order_by(GoodsRequest.created_at.desc())
                .limit(50)
            ).all()
        )
        deleted_sessions = list(
            db.scalars(
                select(DeliverySession)
                .where(DeliverySession.is_deleted.is_(True))
                .options(
                    selectinload(DeliverySession.branch),
                    selectinload(DeliverySession.driver),
                    selectinload(DeliverySession.lines).selectinload(DeliverySessionLine.item),
                )
                .order_by(DeliverySession.started_at.desc())
                .limit(50)
            ).all()
        )
        audit_logs = list(
            db.scalars(
                select(AuditLog)
                .options(selectinload(AuditLog.actor))
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .limit(80)
            ).all()
        )
    analytics = _analytics(db)

    # Chart data: requests per day (last 30 days) using SQL
    today = utc_now().date()
    start_date = today - timedelta(days=29)
    req_counts = db.execute(
        select(
            func.date(GoodsRequest.created_at).label("d"),
            func.count(GoodsRequest.id)
        ).where(GoodsRequest.created_at >= start_date, GoodsRequest.is_deleted.is_(False))
        .group_by(func.date(GoodsRequest.created_at))
    ).all()
    del_counts = db.execute(
        select(
            func.date(DeliverySession.started_at).label("d"),
            func.count(DeliverySession.id)
        ).where(
            DeliverySession.started_at >= start_date,
            DeliverySession.is_deleted.is_(False),
        )
        .group_by(func.date(DeliverySession.started_at))
    ).all()
    req_map = {row[0]: row[1] for row in req_counts}
    del_map = {row[0]: row[1] for row in del_counts}

    chart_labels = []
    chart_requests = []
    chart_deliveries = []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        chart_labels.append(d.strftime("%d.%m"))
        chart_requests.append(req_map.get(d_str, 0))
        chart_deliveries.append(del_map.get(d_str, 0))

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "current_user": current_user,
            "is_super_admin": current_user.is_super_admin,
            "branches": branches,
            "users": users,
            "items": items,
            "requests": requests,
            "demand_lines": demand_lines,
            "sessions": sessions,
            "deleted_requests": deleted_requests,
            "deleted_sessions": deleted_sessions,
            "audit_logs": audit_logs,
            "analytics": analytics,
            "roles": UserRole,
            "message": message,
            "error": error,
            "chart_labels": chart_labels,
            "chart_requests": chart_requests,
            "chart_deliveries": chart_deliveries,
        },
    )


# ─── CRUD ────────────────────────────────────────────────────────────────────

@router.post("/branches")
def add_branch(name: str = Form(...), address: str = Form(""), db: Session = Depends(get_db)):
    name = name.strip()
    if not name:
        return RedirectResponse(
            f"/admin?error={quote('Укажите название подразделения')}#directories",
            status_code=303,
        )
    db.add(Branch(name=name, address=address.strip() or None))
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Подразделение добавлено')}#directories",
        status_code=303,
    )


@router.post("/branches/{branch_id}")
def update_branch(
    branch_id: int,
    name: str = Form(...),
    address: str = Form(""),
    db: Session = Depends(get_db),
):
    branch = db.get(Branch, branch_id)
    if not branch or branch.is_deleted:
        return RedirectResponse(
            f"/admin?error={quote('Подразделение не найдено')}#directories",
            status_code=303,
        )
    name = name.strip()
    if not name:
        return RedirectResponse(
            f"/admin?error={quote('Укажите название подразделения')}#directories",
            status_code=303,
        )
    branch.name = name
    branch.address = address.strip() or None
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Подразделение обновлено')}#directories",
        status_code=303,
    )


@router.post("/items")
def add_item(
    name: str = Form(...),
    unit: str = Form(...),
    unit_cost: float = Form(0),
    db: Session = Depends(get_db),
):
    name = name.strip()
    unit = unit.strip()
    if not name or not unit:
        return RedirectResponse(
            f"/admin?error={quote('Укажите название и единицу измерения')}#items",
            status_code=303,
        )
    db.add(Item(name=name, unit=unit, unit_cost=max(unit_cost, 0)))
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Позиция добавлена')}#items",
        status_code=303,
    )


@router.post("/items/{item_id}")
def update_item(
    item_id: int,
    name: str = Form(...),
    unit: str = Form(...),
    unit_cost: float = Form(0),
    db: Session = Depends(get_db),
):
    item = db.get(Item, item_id)
    if not item or item.is_deleted:
        return RedirectResponse(
            f"/admin?error={quote('Позиция не найдена')}#items", status_code=303
        )
    name = name.strip()
    unit = unit.strip()
    if not name or not unit:
        return RedirectResponse(
            f"/admin?error={quote('Укажите название и единицу измерения')}#items",
            status_code=303,
        )
    item.name = name
    item.unit = unit
    item.unit_cost = max(unit_cost, 0)
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Позиция обновлена')}#items", status_code=303
    )


@router.post("/items/{item_id}/cost")
def update_item_cost(
    item_id: int,
    unit_cost: float = Form(0),
    db: Session = Depends(get_db),
):
    item = db.get(Item, item_id)
    if item and not item.is_deleted:
        item.unit_cost = max(unit_cost, 0)
        db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Цена позиции обновлена')}#items", status_code=303
    )


@router.post("/users")
def add_user(
    full_name: str = Form(...),
    login: str = Form(...),
    password: str = Form(...),
    role: UserRole = Form(...),
    branch_id: str = Form(""),
    db: Session = Depends(get_db),
):
    login = login.strip()
    password = password.strip()
    if not login or not password:
        return RedirectResponse(
            f"/admin?error={quote('Укажите логин и пароль')}#directories", status_code=303
        )
    try:
        parsed_branch_id = int(branch_id) if branch_id.strip() else None
    except ValueError:
        return RedirectResponse(
            f"/admin?error={quote('Некорректное подразделение')}#directories",
            status_code=303,
        )
    if role == UserRole.appraiser and not parsed_branch_id:
        return RedirectResponse(
            f"/admin?error={quote('Для товароведа выберите подразделение')}#directories",
            status_code=303,
        )
    if parsed_branch_id:
        branch = db.get(Branch, parsed_branch_id)
        if not branch or branch.is_deleted or (role == UserRole.appraiser and not branch.is_active):
            return RedirectResponse(
                f"/admin?error={quote('Выбранное подразделение недоступно')}#directories",
                status_code=303,
            )
    existing_deleted = db.scalar(select(User).where(User.login == login, User.is_deleted.is_(True)))
    if existing_deleted:
        existing_deleted.full_name = full_name.strip()
        existing_deleted.password_hash = hash_password(password)
        existing_deleted.role = role
        existing_deleted.branch_id = parsed_branch_id if role == UserRole.appraiser else None
        existing_deleted.is_active = True
        existing_deleted.is_deleted = False
        db.commit()
        return RedirectResponse(
            f"/admin?message={quote('Пользователь восстановлен и обновлён')}#directories",
            status_code=303,
        )
    if db.scalar(select(User).where(User.login == login, User.is_deleted.is_(False))):
        return RedirectResponse(
            f"/admin?error={quote('Пользователь с таким логином уже есть')}#directories",
            status_code=303,
        )
    db.add(
        User(
            full_name=full_name.strip(),
            login=login,
            password_hash=hash_password(password),
            role=role,
            branch_id=parsed_branch_id if role == UserRole.appraiser else None,
        )
    )
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Пользователь добавлен')}#directories", status_code=303
    )


@router.post("/users/{user_id}")
def update_user(
    user_id: int,
    full_name: str = Form(...),
    login: str = Form(...),
    role: UserRole = Form(...),
    branch_id: str = Form(""),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user or user.is_deleted:
        return RedirectResponse(
            f"/admin?error={quote('Пользователь не найден')}#directories", status_code=303
        )

    full_name = full_name.strip()
    login = login.strip()
    if not full_name or not login:
        return RedirectResponse(
            f"/admin?error={quote('Укажите ФИО и логин')}#directories", status_code=303
        )

    duplicate = db.scalar(
        select(User).where(User.login == login, User.id != user_id, User.is_deleted.is_(False))
    )
    if duplicate:
        return RedirectResponse(
            f"/admin?error={quote('Пользователь с таким логином уже есть')}#directories",
            status_code=303,
        )

    try:
        parsed_branch_id = int(branch_id) if branch_id.strip() else None
    except ValueError:
        return RedirectResponse(
            f"/admin?error={quote('Некорректное подразделение')}#directories",
            status_code=303,
        )
    if role == UserRole.appraiser and not parsed_branch_id:
        return RedirectResponse(
            f"/admin?error={quote('Для товароведа выберите подразделение')}#directories",
            status_code=303,
        )
    if parsed_branch_id:
        branch = db.get(Branch, parsed_branch_id)
        if not branch or branch.is_deleted:
            return RedirectResponse(
                f"/admin?error={quote('Выбранное подразделение недоступно')}#directories",
                status_code=303,
            )
    deleted_duplicate = db.scalar(
        select(User).where(User.login == login, User.id != user_id, User.is_deleted.is_(True))
    )
    if deleted_duplicate:
        return RedirectResponse(
            f"/admin?error={quote('Этот логин занят удалённым пользователем. Создайте пользователя с этим логином заново, чтобы восстановить запись.')}#directories",
            status_code=303,
        )

    if user.role == UserRole.admin and role != UserRole.admin and len(_active_admins(db)) <= 1:
        return RedirectResponse(
            f"/admin?error={quote('Нельзя убрать роль у единственного активного администратора')}#directories",
            status_code=303,
        )

    user.full_name = full_name
    user.login = login
    user.role = role
    user.branch_id = parsed_branch_id if role == UserRole.appraiser else None
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Пользователь обновлён')}#directories", status_code=303
    )


@router.post("/users/{user_id}/password")
def reset_user_password(
    user_id: int,
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user or user.is_deleted:
        return RedirectResponse(
            f"/admin?error={quote('Пользователь не найден')}#directories", status_code=303
        )
    password = password.strip()
    if not password:
        return RedirectResponse(
            f"/admin?error={quote('Укажите новый пароль')}#directories", status_code=303
        )
    user.password_hash = hash_password(password)
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Пароль обновлён')}#directories", status_code=303
    )


@router.post("/branches/{branch_id}/toggle")
def toggle_branch(branch_id: int, db: Session = Depends(get_db)):
    branch = db.get(Branch, branch_id)
    if branch and not branch.is_deleted:
        branch.is_active = not branch.is_active
        db.commit()
    return RedirectResponse("/admin#directories", status_code=303)


@router.post("/branches/{branch_id}/delete")
def delete_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    if response := _super_admin_error(current_user):
        return response
    branch = db.get(Branch, branch_id)
    if not branch or branch.is_deleted:
        return RedirectResponse(
            f"/admin?error={quote('Подразделение не найдено')}#directories",
            status_code=303,
        )
    branch.is_deleted = True
    branch.is_active = False
    affected_users = 0
    for branch_user in db.scalars(
        select(User).where(User.branch_id == branch.id, User.is_deleted.is_(False))
    ).all():
        branch_user.is_active = False
        affected_users += 1
    cancelled = _cancel_demand_lines(
        db, current_user, branch_id=branch.id, reason="Подразделение удалено"
    )
    _audit(
        db,
        current_user,
        "delete",
        "branch",
        branch.id,
        f"Подразделение удалено, потребностей отменено: {cancelled}, пользователей отключено: {affected_users}",
    )
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Подразделение удалено')}#directories",
        status_code=303,
    )


@router.get("/branches/{branch_id}/delete")
def delete_branch_get_fallback(branch_id: int):
    return RedirectResponse(
        f"/admin?error={quote('Удаление выполняется только кнопкой формы. Обновите страницу и нажмите «Удалить» ещё раз.')}#directories",
        status_code=303,
    )


@router.post("/items/{item_id}/toggle")
def toggle_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if item and not item.is_deleted:
        item.is_active = not item.is_active
        db.commit()
    return RedirectResponse("/admin#items", status_code=303)


@router.post("/items/{item_id}/delete")
def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    if response := _super_admin_error(current_user):
        return response
    item = db.get(Item, item_id)
    if not item or item.is_deleted:
        return RedirectResponse(
            f"/admin?error={quote('Позиция не найдена')}#items", status_code=303
        )
    item.is_deleted = True
    item.is_active = False
    cancelled = _cancel_demand_lines(
        db, current_user, item_id=item.id, reason="Позиция удалена"
    )
    _audit(
        db,
        current_user,
        "delete",
        "item",
        item.id,
        f"Позиция удалена, потребностей отменено: {cancelled}",
    )
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Позиция удалена')}#items", status_code=303
    )


@router.get("/items/{item_id}/delete")
def delete_item_get_fallback(item_id: int):
    return RedirectResponse(
        f"/admin?error={quote('Удаление выполняется только кнопкой формы. Обновите страницу и нажмите «Удалить» ещё раз.')}#items",
        status_code=303,
    )


@router.post("/users/{user_id}/toggle")
def toggle_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user and not user.is_deleted:
        if user.role == UserRole.admin and user.is_active and len(_active_admins(db)) <= 1:
            return RedirectResponse(
                f"/admin?error={quote('Нельзя отключить единственного активного администратора')}#directories",
                status_code=303,
            )
        user.is_active = not user.is_active
        db.commit()
    return RedirectResponse("/admin#directories", status_code=303)


@router.post("/users/{user_id}/delete")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    if response := _super_admin_error(current_user):
        return response
    user = db.get(User, user_id)
    if not user or user.is_deleted:
        return RedirectResponse(
            f"/admin?error={quote('Пользователь не найден')}#directories", status_code=303
        )
    if user.id == current_user.id:
        return RedirectResponse(
            f"/admin?error={quote('Нельзя удалить текущего пользователя')}#directories",
            status_code=303,
        )
    if user.role == UserRole.admin and user.is_active and len(_active_admins(db)) <= 1:
        return RedirectResponse(
            f"/admin?error={quote('Нельзя удалить единственного активного администратора')}#directories",
            status_code=303,
        )
    user.is_deleted = True
    user.is_active = False
    user.is_super_admin = False
    _audit(db, current_user, "delete", "user", user.id, "Пользователь удалён")
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Пользователь удалён')}#directories",
        status_code=303,
    )


@router.get("/users/{user_id}/delete")
def delete_user_get_fallback(user_id: int):
    return RedirectResponse(
        f"/admin?error={quote('Удаление выполняется только кнопкой формы. Обновите страницу и нажмите «Удалить» ещё раз.')}#directories",
        status_code=303,
    )


@router.post("/demand-lines/{line_id}/delete")
def delete_demand_line(
    line_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    if response := _super_admin_error(current_user):
        return response
    demand_line = db.get(DemandLine, line_id)
    if not demand_line:
        return RedirectResponse(
            f"/admin?error={quote('Потребность не найдена')}#demand", status_code=303
        )
    demand_line.qty_remaining = 0
    demand_line.status = DemandStatus.cancelled
    demand_line.last_updated_at = utc_now()
    _audit(db, current_user, "delete", "demand_line", demand_line.id, "Потребность удалена")
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Потребность удалена')}#demand", status_code=303
    )


@router.get("/demand-lines/{line_id}/delete")
def delete_demand_line_get_fallback(line_id: int):
    return RedirectResponse(
        f"/admin?error={quote('Удаление выполняется только кнопкой формы. Обновите страницу и нажмите «Удалить» ещё раз.')}#demand",
        status_code=303,
    )


@router.post("/requests/{request_id}")
async def update_request(
    request_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    form = await request.form()
    goods_request = db.scalar(
        select(GoodsRequest)
        .where(GoodsRequest.id == request_id)
        .options(selectinload(GoodsRequest.lines))
    )
    if not goods_request:
        return RedirectResponse(
            f"/admin?error={quote('Заявка не найдена')}#history", status_code=303
        )
    if goods_request.is_deleted:
        return RedirectResponse(
            f"/admin?error={quote('Заявка уже удалена')}#history", status_code=303
        )

    line_ids = form.getlist("line_id")
    qty_values = form.getlist("qty_requested")
    comments = form.getlist("line_comment")
    lines_by_id = {line.id: line for line in goods_request.lines}
    try:
        for line_id_raw, qty_raw, comment_raw in zip(line_ids, qty_values, comments, strict=False):
            line_id = int(line_id_raw)
            line = lines_by_id.get(line_id)
            if not line:
                raise ValueError("Строка заявки не найдена.")
            qty = _parse_decimal(qty_raw, "Количество")
            line.qty_requested = qty
            line.comment = str(comment_raw or "").strip() or None
    except (ValueError, InvalidOperation) as exc:
        db.rollback()
        return RedirectResponse(
            f"/admin?error={quote(str(exc))}#history", status_code=303
        )

    goods_request.comment = str(form.get("comment") or "").strip() or None
    goods_request.status = RequestStatus.processed
    await run_in_threadpool(_recalculate_all_demand, db)
    await run_in_threadpool(_audit, db, current_user, "update", "request", request_id, "Заявка обновлена")
    await run_in_threadpool(db.commit)
    return RedirectResponse(
        f"/admin?message={quote('Заявка обновлена')}#history", status_code=303
    )


@router.post("/requests/{request_id}/delete")
def delete_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    goods_request = db.scalar(
        select(GoodsRequest)
        .where(GoodsRequest.id == request_id)
        .options(selectinload(GoodsRequest.lines))
    )
    if not goods_request:
        return RedirectResponse(
            f"/admin?error={quote('Заявка не найдена')}#history", status_code=303
        )
    if goods_request.is_deleted:
        return RedirectResponse(
            f"/admin?message={quote('Заявка уже удалена')}#history", status_code=303
        )
    try:
        goods_request.is_deleted = True
        _recalculate_all_demand(db)
        _audit(db, current_user, "soft_delete", "request", request_id, "Заявка удалена из истории")
        db.commit()
    except ValueError as exc:
        db.rollback()
        return RedirectResponse(
            f"/admin?error={quote(str(exc))}#history", status_code=303
        )
    return RedirectResponse(
        f"/admin?message={quote('Заявка удалена')}#history", status_code=303
    )


@router.get("/requests/{request_id}/delete")
def delete_request_get_fallback(request_id: int):
    return RedirectResponse(
        f"/admin?error={quote('Удаление выполняется только кнопкой формы. Обновите страницу и нажмите «Удалить» ещё раз.')}#history",
        status_code=303,
    )


@router.post("/delivery-sessions/{session_id}")
async def update_delivery_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    form = await request.form()
    session = db.scalar(
        select(DeliverySession)
        .where(DeliverySession.id == session_id)
        .options(selectinload(DeliverySession.lines))
    )
    if not session:
        return RedirectResponse(
            f"/admin?error={quote('Визит не найден')}#history", status_code=303
        )
    if session.is_deleted:
        return RedirectResponse(
            f"/admin?error={quote('Визит уже удалён')}#history", status_code=303
        )

    line_ids = form.getlist("line_id")
    qty_values = form.getlist("qty_delivered_now")
    lines_by_id = {line.id: line for line in session.lines}
    try:
        for line_id_raw, qty_raw in zip(line_ids, qty_values, strict=False):
            line_id = int(line_id_raw)
            line = lines_by_id.get(line_id)
            if not line:
                raise ValueError("Строка визита не найдена.")
            qty = _parse_non_negative_decimal(qty_raw, "Доставлено")
            qty_before = Decimal(line.qty_before)
            if qty > qty_before:
                raise ValueError("Нельзя доставить больше остатка в строке визита.")
            line.qty_delivered_now = qty
            line.qty_after = qty_before - qty
            line.result_status = _result_status(qty, Decimal(line.qty_after))
    except (ValueError, InvalidOperation) as exc:
        db.rollback()
        return RedirectResponse(
            f"/admin?error={quote(str(exc))}#history", status_code=303
        )

    await run_in_threadpool(_recalculate_all_demand, db)
    await run_in_threadpool(_audit, db, current_user, "update", "delivery_session", session_id, "Визит обновлён")
    await run_in_threadpool(db.commit)
    return RedirectResponse(
        f"/admin?message={quote('Визит обновлён')}#history", status_code=303
    )


@router.post("/delivery-sessions/{session_id}/delete")
def delete_delivery_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    session = db.scalar(
        select(DeliverySession)
        .where(DeliverySession.id == session_id)
        .options(selectinload(DeliverySession.lines))
    )
    if not session:
        return RedirectResponse(
            f"/admin?error={quote('Визит не найден')}#history", status_code=303
        )
    if session.is_deleted:
        return RedirectResponse(
            f"/admin?message={quote('Визит уже удалён')}#history", status_code=303
        )
    try:
        session.is_deleted = True
        session.status = DeliverySessionStatus.closed
        session.finished_at = session.finished_at or utc_now()
        _recalculate_all_demand(db)
        _audit(
            db,
            current_user,
            "soft_delete",
            "delivery_session",
            session_id,
            "Визит удалён из истории и отчётов",
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        return RedirectResponse(
            f"/admin?error={quote(str(exc))}#history", status_code=303
        )
    return RedirectResponse(
        f"/admin?message={quote('Визит удалён из истории и отчётов')}#history", status_code=303
    )


@router.get("/delivery-sessions/{session_id}/delete")
def delete_delivery_session_get_fallback(session_id: int):
    return RedirectResponse(
        f"/admin?error={quote('Удаление выполняется только кнопкой формы. Обновите страницу и нажмите «Удалить» ещё раз.')}#history",
        status_code=303,
    )


@router.post("/requests/{request_id}/restore")
def restore_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    if response := _super_admin_error(current_user):
        return response
    goods_request = db.get(GoodsRequest, request_id)
    if not goods_request:
        return RedirectResponse(
            f"/admin?error={quote('Заявка не найдена')}#super", status_code=303
        )
    goods_request.is_deleted = False
    _recalculate_all_demand(db)
    _audit(db, current_user, "restore", "request", request_id, "Заявка восстановлена")
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Заявка восстановлена')}#super", status_code=303
    )


@router.post("/requests/{request_id}/purge")
def purge_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    if response := _super_admin_error(current_user):
        return response
    goods_request = db.get(GoodsRequest, request_id)
    if not goods_request:
        return RedirectResponse(
            f"/admin?error={quote('Заявка не найдена')}#super", status_code=303
        )
    if not goods_request.is_deleted:
        return RedirectResponse(
            f"/admin?error={quote('Сначала удалите заявку из истории')}#super", status_code=303
        )
    db.delete(goods_request)
    _recalculate_all_demand(db)
    _audit(db, current_user, "purge", "request", request_id, "Заявка удалена навсегда")
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Заявка удалена навсегда')}#super", status_code=303
    )


@router.post("/delivery-sessions/{session_id}/restore")
def restore_delivery_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    if response := _super_admin_error(current_user):
        return response
    session = db.get(DeliverySession, session_id)
    if not session:
        return RedirectResponse(
            f"/admin?error={quote('Визит не найден')}#super", status_code=303
        )
    session.is_deleted = False
    _recalculate_all_demand(db)
    _audit(db, current_user, "restore", "delivery_session", session_id, "Визит восстановлен")
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Визит восстановлен')}#super", status_code=303
    )


@router.post("/delivery-sessions/{session_id}/purge")
def purge_delivery_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    if response := _super_admin_error(current_user):
        return response
    session = db.get(DeliverySession, session_id)
    if not session:
        return RedirectResponse(
            f"/admin?error={quote('Визит не найден')}#super", status_code=303
        )
    if not session.is_deleted:
        return RedirectResponse(
            f"/admin?error={quote('Сначала удалите визит из истории')}#super", status_code=303
        )
    db.delete(session)
    _recalculate_all_demand(db)
    _audit(db, current_user, "purge", "delivery_session", session_id, "Визит удалён навсегда")
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Визит удалён навсегда')}#super", status_code=303
    )


@router.post("/users/{user_id}/super-toggle")
def toggle_super_admin(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    if response := _super_admin_error(current_user):
        return response
    user = db.get(User, user_id)
    if not user or user.is_deleted:
        return RedirectResponse(
            f"/admin?error={quote('Пользователь не найден')}#directories", status_code=303
        )
    if user.id == current_user.id:
        return RedirectResponse(
            f"/admin?error={quote('Нельзя снять суперадмина с текущего пользователя')}#directories",
            status_code=303,
        )
    user.is_super_admin = not user.is_super_admin
    if user.is_super_admin:
        user.role = UserRole.admin
        user.is_active = True
    _audit(
        db,
        current_user,
        "toggle_super_admin",
        "user",
        user.id,
        f"is_super_admin={user.is_super_admin}",
    )
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Права суперадмина обновлены')}#directories",
        status_code=303,
    )


@router.post("/super/recalculate")
def recalculate_demand(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    if response := _super_admin_error(current_user):
        return response
    _recalculate_all_demand(db)
    _audit(db, current_user, "recalculate", "demand", None, "Активные потребности пересчитаны")
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Активные потребности пересчитаны')}#super",
        status_code=303,
    )


@router.post("/super/cleanup")
def cleanup_period(
    date_from: str = Form(""),
    date_to: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    if response := _super_admin_error(current_user):
        return response
    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    if not df and not dt:
        return RedirectResponse(
            f"/admin?error={quote('Укажите период очистки')}#super", status_code=303
        )
    request_query = select(GoodsRequest).where(GoodsRequest.is_deleted.is_(False))
    session_query = select(DeliverySession).where(DeliverySession.is_deleted.is_(False))
    if df:
        request_query = request_query.where(GoodsRequest.created_at >= df)
        session_query = session_query.where(DeliverySession.started_at >= df)
    if dt:
        request_query = request_query.where(GoodsRequest.created_at < dt + timedelta(days=1))
        session_query = session_query.where(DeliverySession.started_at < dt + timedelta(days=1))

    requests = list(db.scalars(request_query).all())
    sessions = list(db.scalars(session_query).all())
    for goods_request in requests:
        goods_request.is_deleted = True
    for session in sessions:
        session.is_deleted = True
        session.status = DeliverySessionStatus.closed
        session.finished_at = session.finished_at or utc_now()
    _recalculate_all_demand(db)
    _audit(
        db,
        current_user,
        "cleanup",
        "period",
        None,
        f"{date_from or 'начало'}..{date_to or 'сегодня'}: requests={len(requests)}, sessions={len(sessions)}",
    )
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote(f'Тестовые данные скрыты: заявок {len(requests)}, визитов {len(sessions)}')}#super",
        status_code=303,
    )


@router.get("/super/backup")
def download_database_backup(current_user: User = Depends(require_roles(UserRole.admin))):
    if not current_user.is_super_admin:
        return RedirectResponse(
            f"/admin?error={quote('Действие доступно только суперадмину')}#super",
            status_code=303,
        )
    if not DATABASE_URL.startswith("sqlite:///") or not DATABASE_PATH.exists():
        return RedirectResponse(
            f"/admin?error={quote('Резервная копия доступна только для файловой SQLite-базы')}#super",
            status_code=303,
        )
    filename = f"sklad_requests_backup_{utc_now().strftime('%Y%m%d_%H%M%S')}.db"
    return FileResponse(
        DATABASE_PATH,
        media_type="application/octet-stream",
        filename=filename,
    )


# ─── Helper: build export data with date filters ────────────────────────────

def _get_request_rows(db: Session, date_from: datetime | None, date_to: datetime | None) -> list[dict]:
    query = (
        select(GoodsRequest)
        .where(GoodsRequest.is_deleted.is_(False))
        .options(
            selectinload(GoodsRequest.branch),
            selectinload(GoodsRequest.created_by),
            selectinload(GoodsRequest.lines).selectinload(RequestLine.item),
        )
        .order_by(GoodsRequest.created_at.desc())
    )
    if date_from:
        query = query.where(GoodsRequest.created_at >= date_from)
    if date_to:
        query = query.where(GoodsRequest.created_at < date_to + timedelta(days=1))
    requests = list(db.scalars(query).all())
    return [
        {
            "request_id": request.id,
            "created_at": request.created_at.strftime("%d.%m.%Y %H:%M"),
            "branch": request.branch.name,
            "created_by": request.created_by.full_name,
            "item": line.item.name,
            "unit": line.item.unit,
            "unit_cost": _money(line.item.unit_cost),
            "qty_requested": float(line.qty_requested),
            "requested_cost": _money(float(line.qty_requested) * float(line.item.unit_cost or 0)),
            "status": request.status.value,
            "comment": request.comment or "",
            "line_comment": line.comment or "",
        }
        for request in requests
        for line in request.lines
        if not request.branch.is_deleted
        and not request.created_by.is_deleted
        and not line.item.is_deleted
    ]


def _get_delivery_rows(db: Session, date_from: datetime | None, date_to: datetime | None) -> list[dict]:
    query = (
        select(DeliverySession)
        .where(DeliverySession.is_deleted.is_(False))
        .options(
            selectinload(DeliverySession.branch),
            selectinload(DeliverySession.driver),
            selectinload(DeliverySession.lines).selectinload(DeliverySessionLine.item),
        )
        .order_by(DeliverySession.started_at.desc())
    )
    if date_from:
        query = query.where(DeliverySession.started_at >= date_from)
    if date_to:
        query = query.where(DeliverySession.started_at < date_to + timedelta(days=1))
    sessions = list(db.scalars(query).all())
    return [
        {
            "session_id": session.id,
            "started_at": session.started_at.strftime("%d.%m.%Y %H:%M"),
            "finished_at": session.finished_at.strftime("%d.%m.%Y %H:%M") if session.finished_at else "",
            "driver": session.driver.full_name,
            "branch": session.branch.name,
            "item": line.item.name,
            "unit": line.item.unit,
            "unit_cost": _money(line.item.unit_cost),
            "qty_before": float(line.qty_before),
            "qty_delivered_now": float(line.qty_delivered_now),
            "delivered_cost": _money(float(line.qty_delivered_now) * float(line.item.unit_cost or 0)),
            "qty_after": float(line.qty_after),
            "result_status": line.result_status.value,
            "session_status": session.status.value,
        }
        for session in sessions
        for line in session.lines
        if not session.branch.is_deleted
        and not session.driver.is_deleted
        and not line.item.is_deleted
    ]


# ─── Excel exports with date range ──────────────────────────────────────────

@router.get("/export/requests.xlsx")
def export_requests_xlsx(
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
):
    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    rows = _get_request_rows(db, df, dt)
    suffix = f"_{date_from}_{date_to}" if date_from or date_to else ""
    buf = build_requests_xlsx(rows)
    return _xlsx_response(f"requests{suffix}.xlsx", buf)


@router.get("/export/deliveries.xlsx")
def export_deliveries_xlsx(
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
):
    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    rows = _get_delivery_rows(db, df, dt)
    suffix = f"_{date_from}_{date_to}" if date_from or date_to else ""
    buf = build_deliveries_xlsx(rows)
    return _xlsx_response(f"deliveries{suffix}.xlsx", buf)


@router.get("/export/active-demand.xlsx")
def export_demand_xlsx(db: Session = Depends(get_db)):
    lines = list(
        db.scalars(
            select(DemandLine)
            .options(selectinload(DemandLine.branch), selectinload(DemandLine.item))
            .order_by(DemandLine.branch_id, DemandLine.item_id)
        ).all()
    )
    rows = [
        {
            "branch": line.branch.name,
            "address": line.branch.address or "",
            "item": line.item.name,
            "unit": line.item.unit,
            "unit_cost": _money(line.item.unit_cost),
            "qty_requested": float(line.qty_total_requested),
            "qty_delivered": float(line.qty_total_delivered),
            "qty_remaining": float(line.qty_remaining),
            "remaining_cost": _money(float(line.qty_remaining) * float(line.item.unit_cost or 0)),
            "status": line.status.value,
        }
        for line in lines
        if line.status in (DemandStatus.active, DemandStatus.partially_delivered)
        and not line.branch.is_deleted
        and not line.item.is_deleted
    ]
    buf = build_demand_xlsx(rows)
    return _xlsx_response("active-demand.xlsx", buf)


@router.get("/export/summary.xlsx")
def export_summary_xlsx(
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
):
    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    analytics = _analytics(db, df, dt)
    buf = build_summary_xlsx(analytics, date_from or "начало", date_to or "сегодня")
    return _xlsx_response("summary.xlsx", buf)


# ─── Legacy CSV exports (kept for compatibility) ────────────────────────────

@router.get("/export/active-demand.csv")
def export_active_demand(db: Session = Depends(get_db)):
    lines = list(
        db.scalars(
            select(DemandLine)
            .options(selectinload(DemandLine.branch), selectinload(DemandLine.item))
            .order_by(DemandLine.branch_id, DemandLine.item_id)
        ).all()
    )
    rows = [
        {
            "branch": line.branch.name,
            "address": line.branch.address or "",
            "item": line.item.name,
            "unit": line.item.unit,
            "unit_cost": _money(line.item.unit_cost),
            "qty_requested": float(line.qty_total_requested),
            "qty_delivered": float(line.qty_total_delivered),
            "qty_remaining": float(line.qty_remaining),
            "remaining_cost": _money(float(line.qty_remaining) * float(line.item.unit_cost or 0)),
            "status": line.status.value,
        }
        for line in lines
        if line.status in (DemandStatus.active, DemandStatus.partially_delivered)
        and not line.branch.is_deleted
        and not line.item.is_deleted
    ]
    return _csv_response("active-demand.csv", rows)


@router.get("/export/requests.csv")
def export_requests(
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
):
    rows = _get_request_rows(db, _parse_date(date_from), _parse_date(date_to))
    return _csv_response("requests.csv", rows)


@router.get("/export/deliveries.csv")
def export_deliveries(
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
):
    rows = _get_delivery_rows(db, _parse_date(date_from), _parse_date(date_to))
    return _csv_response("deliveries.csv", rows)


@router.get("/export/summary.csv")
def export_summary(db: Session = Depends(get_db)):
    analytics = _analytics(db)
    rows = [
        {"metric": "active_branches", "value": analytics["active_branches"]},
        {"metric": "active_positions", "value": analytics["active_positions"]},
        {"metric": "active_qty", "value": _money(analytics["active_qty"])},
        {"metric": "active_cost", "value": _money(analytics["active_cost"])},
        {"metric": "requested_qty", "value": _money(analytics["requested_qty"])},
        {"metric": "requested_cost", "value": _money(analytics["requested_cost"])},
        {"metric": "delivered_qty", "value": _money(analytics["delivered_qty"])},
        {"metric": "delivered_cost", "value": _money(analytics["delivered_cost"])},
        {"metric": "delivery_sessions", "value": analytics["delivery_sessions_count"]},
    ]
    return _csv_response("summary.csv", rows)
