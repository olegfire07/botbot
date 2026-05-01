"""HTMX endpoints for loading dashboard tabs."""

import logging
from datetime import timedelta

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import or_, select
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
)
from app.routers.admin import router, templates
from app.routers.admin._helpers import (
    _clean_filter,
    _numeric_filter,
    _parse_date,
    _text_contains,
)

logger = logging.getLogger(__name__)


@router.get("/tabs/items", response_class=HTMLResponse)
def get_items_tab(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    items = list(
        db.scalars(select(Item).where(Item.is_deleted.is_(False)).order_by(Item.name)).all()
    )
    return templates.TemplateResponse(
        "admin/tabs/items.html",
        {
            "request": request,
            "current_user": current_user,
            "is_super_admin": current_user.is_super_admin,
            "items": items,
        },
    )


@router.get("/tabs/directories", response_class=HTMLResponse)
def get_directories_tab(
    request: Request,
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
    return templates.TemplateResponse(
        "admin/tabs/directories.html",
        {
            "request": request,
            "current_user": current_user,
            "is_super_admin": current_user.is_super_admin,
            "branches": branches,
            "users": users,
        },
    )


@router.get("/tabs/demand", response_class=HTMLResponse)
def get_demand_tab(
    request: Request,
    demand_q: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    demand_q = _clean_filter(demand_q)
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
    return templates.TemplateResponse(
        "admin/tabs/demand.html",
        {
            "request": request,
            "current_user": current_user,
            "is_super_admin": current_user.is_super_admin,
            "demand_lines": demand_lines,
            "demand_q": demand_q,
        },
    )


@router.get("/tabs/history", response_class=HTMLResponse)
def get_history_tab(
    request: Request,
    history_q: str | None = None,
    history_date_from: str | None = None,
    history_date_to: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    history_q = _clean_filter(history_q)
    history_date_from = _clean_filter(history_date_from, 10)
    history_date_to = _clean_filter(history_date_to, 10)
    history_from_dt = _parse_date(history_date_from)
    history_to_dt = _parse_date(history_date_to)

    # Base query for requests
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
            .limit(limit)
        ).all()
    )

    # Base query for sessions
    session_ids = (
        select(DeliverySession.id)
        .select_from(DeliverySession)
        .join(Branch, Branch.id == DeliverySession.branch_id)
        .join(User, User.id == DeliverySession.driver_id)
        .outerjoin(DeliverySessionLine, DeliverySessionLine.delivery_session_id == DeliverySession.id)
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
            .limit(limit)
        ).all()
    )

    return templates.TemplateResponse(
        "admin/tabs/history.html",
        {
            "request": request,
            "current_user": current_user,
            "is_super_admin": current_user.is_super_admin,
            "requests": requests,
            "sessions": sessions,
            "limit": limit,
            "history_q": history_q,
            "history_date_from": history_date_from,
            "history_date_to": history_date_to,
            "history_filters_active": bool(history_q or history_date_from or history_date_to),
            "has_more": len(requests) == limit or len(sessions) == limit,
        },
    )


@router.get("/tabs/super", response_class=HTMLResponse)
def get_super_tab(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    if not current_user.is_super_admin:
        return HTMLResponse("Доступ запрещён", status_code=403)

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
    return templates.TemplateResponse(
        "admin/tabs/super.html",
        {
            "request": request,
            "current_user": current_user,
            "is_super_admin": True,
            "deleted_requests": deleted_requests,
            "deleted_sessions": deleted_sessions,
            "audit_logs": audit_logs,
        },
    )
