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
            "analytics": analytics,
            "roles": UserRole,
            "message": message,
            "error": error,
            "chart_labels": chart_labels,
            "chart_requests": chart_requests,
            "chart_deliveries": chart_deliveries,
            "history_filters_active": False,
        },
    )
