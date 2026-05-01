"""CSV/XLSX export endpoints and database backup."""

import logging
from datetime import datetime, timedelta
from io import BytesIO

from fastapi import Depends
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import DATABASE_PATH, DATABASE_URL, get_db
from app.models import (
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
from app.routers.admin import router
from app.routers.admin._helpers import _csv_response, _money, _parse_date, _xlsx_response
from app.routers.admin.dashboard import _analytics
from app.services.excel_service import (
    build_deliveries_xlsx,
    build_demand_xlsx,
    build_requests_xlsx,
    build_summary_xlsx,
)

logger = logging.getLogger(__name__)


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
            "shortage_reason": line.shortage_reason or "",
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
