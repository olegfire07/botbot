from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DemandLine, DemandStatus, utc_now


ACTIVE_DEMAND_STATUSES = (DemandStatus.active, DemandStatus.partially_delivered)


def recalculate_demand_status(demand_line: DemandLine) -> None:
    demand_line.qty_remaining = Decimal(demand_line.qty_total_requested) - Decimal(
        demand_line.qty_total_delivered
    )
    if Decimal(demand_line.qty_remaining) <= 0:
        demand_line.qty_remaining = 0
        demand_line.status = DemandStatus.delivered
    elif Decimal(demand_line.qty_total_delivered) == 0:
        demand_line.status = DemandStatus.active
    else:
        demand_line.status = DemandStatus.partially_delivered
    demand_line.last_updated_at = utc_now()


def get_active_demand_lines(db: Session, branch_id: int) -> list[DemandLine]:
    return list(
        db.scalars(
            select(DemandLine)
            .where(
                DemandLine.branch_id == branch_id,
                DemandLine.status.in_(ACTIVE_DEMAND_STATUSES),
            )
            .order_by(DemandLine.last_updated_at.desc(), DemandLine.id.desc())
        ).all()
    )


def add_or_update_demand_line(
    db: Session, branch_id: int, item_id: int, qty: float | Decimal
) -> DemandLine:
    qty_decimal = Decimal(str(qty))
    demand_line = db.scalar(
        select(DemandLine).where(
            DemandLine.branch_id == branch_id,
            DemandLine.item_id == item_id,
            DemandLine.status.in_(ACTIVE_DEMAND_STATUSES),
        ).with_for_update()
    )
    if demand_line:
        demand_line.qty_total_requested = Decimal(demand_line.qty_total_requested) + qty_decimal
        demand_line.qty_remaining = Decimal(demand_line.qty_remaining) + qty_decimal
        recalculate_demand_status(demand_line)
        return demand_line

    demand_line = DemandLine(
        branch_id=branch_id,
        item_id=item_id,
        qty_total_requested=qty_decimal,
        qty_total_delivered=0,
        qty_remaining=qty_decimal,
        status=DemandStatus.active,
    )
    db.add(demand_line)
    return demand_line
