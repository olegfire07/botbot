"""Demand-line recalculation logic for the admin panel."""

import logging
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Branch,
    DeliverySession,
    DeliverySessionLine,
    DemandLine,
    DemandStatus,
    Item,
    Request as GoodsRequest,
    RequestLine,
    utc_now,
)
from app.services.demand_service import ACTIVE_DEMAND_STATUSES, recalculate_demand_status

from app.routers.admin._helpers import _audit

logger = logging.getLogger(__name__)


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
    actor,
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


def _recalculate_all_demand(db: Session) -> None:
    """Full recalculation of all demand lines from scratch."""
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

    logger.info("Full demand recalculation complete: %d keys processed", len(all_keys))


def recalculate_demand_for_keys(
    db: Session, keys: set[tuple[int, int]]
) -> None:
    """Incremental demand recalculation for specific (branch_id, item_id) pairs."""
    if not keys:
        return

    for branch_id, item_id in keys:
        requested_qty = Decimal(
            db.scalar(
                select(func.coalesce(func.sum(RequestLine.qty_requested), 0))
                .select_from(RequestLine)
                .join(GoodsRequest)
                .where(
                    GoodsRequest.branch_id == branch_id,
                    RequestLine.item_id == item_id,
                    GoodsRequest.is_deleted.is_(False),
                )
            ) or 0
        )
        delivered_qty = Decimal(
            db.scalar(
                select(func.coalesce(func.sum(DeliverySessionLine.qty_delivered_now), 0))
                .select_from(DeliverySessionLine)
                .join(DeliverySession)
                .where(
                    DeliverySession.branch_id == branch_id,
                    DeliverySessionLine.item_id == item_id,
                    DeliverySession.is_deleted.is_(False),
                )
            ) or 0
        )

        total_requested = max(requested_qty, delivered_qty)
        demand_line = db.scalar(
            select(DemandLine).where(
                DemandLine.branch_id == branch_id,
                DemandLine.item_id == item_id,
            )
        )

        if not demand_line:
            if total_requested > 0:
                demand_line = DemandLine(
                    branch_id=branch_id,
                    item_id=item_id,
                    qty_total_requested=total_requested,
                    qty_total_delivered=delivered_qty,
                    qty_remaining=total_requested - delivered_qty,
                    status=DemandStatus.active,
                )
                db.add(demand_line)
                recalculate_demand_status(demand_line)
        else:
            demand_line.qty_total_requested = total_requested
            demand_line.qty_total_delivered = delivered_qty
            demand_line.qty_remaining = total_requested - delivered_qty
            recalculate_demand_status(demand_line)

    logger.debug("Incremental demand recalculation for %d keys", len(keys))
