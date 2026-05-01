"""Admin dashboard: overview, analytics, chart data."""

import logging
from datetime import datetime, timedelta

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.auth import require_roles
from app.database import get_db
from app.models import (
    AuditLog,
    Branch,
    DeliverySession,
    DeliverySessionLine,
    DemandLine,
    DemandStatus,
    Item,
    Request as GoodsRequest,
    RequestLine,
    User,
    UserRole,
    utc_now,
)
from app.routers.admin import router, templates
from app.routers.admin._helpers import (
    _clean_filter,
    _numeric_filter,
    _parse_date,
    _text_contains,
)

logger = logging.getLogger(__name__)


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
    demand_q: str | None = None,
    history_q: str | None = None,
    history_date_from: str | None = None,
    history_date_to: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    demand_q = _clean_filter(demand_q)
    history_q = _clean_filter(history_q)
    history_date_from = _clean_filter(history_date_from, 10)
    history_date_to = _clean_filter(history_date_to, 10)
    history_from_dt = _parse_date(history_date_from)
    history_to_dt = _parse_date(history_date_to)
    if history_date_from and not history_from_dt:
        history_date_from = ""
    if history_date_to and not history_to_dt:
        history_date_to = ""

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
    request_ids = (
        select(GoodsRequest.id)
        .select_from(GoodsRequest)
        .join(Branch, Branch.id == GoodsRequest.branch_id)
        .join(User, User.id == GoodsRequest.created_by_user_id)
        .outerjoin(RequestLine, RequestLine.request_id == GoodsRequest.id)
        .outerjoin(Item, Item.id == RequestLine.item_id)
        .where(
            GoodsRequest.is_deleted.is_(False),
            Branch.is_deleted.is_(False),
            User.is_deleted.is_(False),
            or_(Item.id.is_(None), Item.is_deleted.is_(False)),
        )
        .group_by(GoodsRequest.id)
    )
    if history_from_dt:
        request_ids = request_ids.where(GoodsRequest.created_at >= history_from_dt)
    if history_to_dt:
        request_ids = request_ids.where(GoodsRequest.created_at < history_to_dt + timedelta(days=1))
    if history_q:
        request_number = _numeric_filter(history_q)
        request_conditions = [
            _text_contains(Branch.name, history_q),
            _text_contains(Branch.address, history_q),
            _text_contains(User.full_name, history_q),
            _text_contains(User.login, history_q),
            _text_contains(GoodsRequest.comment, history_q),
            _text_contains(Item.name, history_q),
            _text_contains(RequestLine.comment, history_q),
        ]
        if request_number is not None:
            request_conditions.append(GoodsRequest.id == request_number)
        request_ids = request_ids.where(or_(*request_conditions))

    requests = list(
        db.scalars(
            select(GoodsRequest)
            .where(GoodsRequest.id.in_(request_ids))
            .options(
                selectinload(GoodsRequest.branch),
                selectinload(GoodsRequest.created_by),
                selectinload(GoodsRequest.lines).selectinload(RequestLine.item),
            )
            .order_by(GoodsRequest.created_at.desc())
            .limit(100)
        ).all()
    )
    demand_query = (
        select(DemandLine)
        .join(Branch)
        .join(Item)
        .where(DemandLine.status.in_((DemandStatus.active, DemandStatus.partially_delivered)))
        .options(selectinload(DemandLine.branch), selectinload(DemandLine.item))
        .where(Branch.is_deleted.is_(False), Item.is_deleted.is_(False))
    )
    if demand_q:
        demand_number = _numeric_filter(demand_q)
        demand_conditions = [
            _text_contains(Branch.name, demand_q),
            _text_contains(Branch.address, demand_q),
            _text_contains(Item.name, demand_q),
            _text_contains(Item.unit, demand_q),
        ]
        if demand_number is not None:
            demand_conditions.append(DemandLine.id == demand_number)
        demand_query = demand_query.where(or_(*demand_conditions))

    demand_lines = list(
        db.scalars(
            demand_query
            .order_by(DemandLine.last_updated_at.desc())
            .limit(100)
        ).all()
    )
    session_ids = (
        select(DeliverySession.id)
        .select_from(DeliverySession)
        .join(Branch, Branch.id == DeliverySession.branch_id)
        .join(User, User.id == DeliverySession.driver_id)
        .outerjoin(
            DeliverySessionLine,
            DeliverySessionLine.delivery_session_id == DeliverySession.id,
        )
        .outerjoin(Item, Item.id == DeliverySessionLine.item_id)
        .where(
            DeliverySession.is_deleted.is_(False),
            Branch.is_deleted.is_(False),
            User.is_deleted.is_(False),
            or_(Item.id.is_(None), Item.is_deleted.is_(False)),
        )
        .group_by(DeliverySession.id)
    )
    if history_from_dt:
        session_ids = session_ids.where(DeliverySession.started_at >= history_from_dt)
    if history_to_dt:
        session_ids = session_ids.where(DeliverySession.started_at < history_to_dt + timedelta(days=1))
    if history_q:
        session_number = _numeric_filter(history_q)
        session_conditions = [
            _text_contains(Branch.name, history_q),
            _text_contains(Branch.address, history_q),
            _text_contains(User.full_name, history_q),
            _text_contains(User.login, history_q),
            _text_contains(Item.name, history_q),
            _text_contains(Item.unit, history_q),
            _text_contains(DeliverySessionLine.shortage_reason, history_q),
        ]
        if session_number is not None:
            session_conditions.append(DeliverySession.id == session_number)
        session_ids = session_ids.where(or_(*session_conditions))

    sessions = list(
        db.scalars(
            select(DeliverySession)
            .where(DeliverySession.id.in_(session_ids))
            .options(
                selectinload(DeliverySession.branch),
                selectinload(DeliverySession.driver),
                selectinload(DeliverySession.lines).selectinload(DeliverySessionLine.item),
            )
            .order_by(DeliverySession.started_at.desc())
            .limit(100)
        ).all()
    )


    deleted_requests = []
    deleted_sessions = []
    audit_logs = []
    if current_user and current_user.is_super_admin:
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
            "is_super_admin": current_user.is_super_admin if current_user else False,
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
            "demand_q": demand_q,
            "history_q": history_q,
            "history_date_from": history_date_from,
            "history_date_to": history_date_to,
            "history_filters_active": bool(history_q or history_date_from or history_date_to),
        },
    )
