from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Branch,
    DemandLine,
    Item,
    Request,
    RequestLine,
    RequestStatus,
    User,
    UserRole,
    utc_now,
)
from app.schemas import RequestLineInput
from app.services.demand_service import ACTIVE_DEMAND_STATUSES, add_or_update_demand_line


class RequestValidationError(ValueError):
    pass


def _today_open_request(db: Session, appraiser_id: int, branch_id: int) -> Request | None:
    today = utc_now().date()
    starts_at = datetime.combine(today, time.min)
    ends_at = starts_at + timedelta(days=1)
    active_item_ids = set(
        db.scalars(
            select(DemandLine.item_id).where(
                DemandLine.branch_id == branch_id,
                DemandLine.status.in_(ACTIVE_DEMAND_STATUSES),
            )
        ).all()
    )
    if not active_item_ids:
        return None

    return db.scalar(
        select(Request)
        .join(RequestLine)
        .where(
            Request.branch_id == branch_id,
            Request.created_by_user_id == appraiser_id,
            Request.created_at >= starts_at,
            Request.created_at < ends_at,
            Request.status == RequestStatus.processed,
            Request.is_deleted.is_(False),
            RequestLine.item_id.in_(active_item_ids),
        )
        .order_by(Request.created_at.desc(), Request.id.desc())
        .limit(1)
    )


def create_request(
    db: Session,
    appraiser_id: int,
    branch_id: int,
    comment: str | None,
    lines: list[RequestLineInput],
) -> Request:
    if not lines:
        raise RequestValidationError("Нельзя создать заявку без строк.")

    appraiser = db.get(User, appraiser_id)
    if (
        not appraiser
        or appraiser.role != UserRole.appraiser
        or not appraiser.is_active
        or appraiser.is_deleted
    ):
        raise RequestValidationError("Выберите активного товароведа.")

    branch = db.get(Branch, branch_id)
    if not branch or not branch.is_active or branch.is_deleted:
        raise RequestValidationError("Выберите активное подразделение.")

    item_ids = {line.item_id for line in lines if line.item_id > 0}
    active_item_ids = {
        item_id
        for item_id in db.scalars(
            select(Item.id).where(
                Item.id.in_(item_ids),
                Item.is_active.is_(True),
                Item.is_deleted.is_(False),
            )
        ).all()
    }

    for line in lines:
        if line.item_id <= 0:
            raise RequestValidationError("В каждой строке нужно выбрать позицию.")
        if line.item_id not in active_item_ids:
            raise RequestValidationError("В каждой строке нужно выбрать активную позицию.")
        try:
            qty_val = Decimal(str(line.qty_requested))
        except InvalidOperation:
            raise RequestValidationError("Количество должно быть числом.")
        if qty_val <= 0:
            raise RequestValidationError("Количество должно быть больше 0.")

    request = _today_open_request(db, appraiser.id, branch.id)
    if request:
        if comment:
            request.comment = f"{request.comment}\n{comment}" if request.comment else comment
    else:
        request = Request(
            branch_id=branch.id,
            created_by_user_id=appraiser.id,
            comment=comment or None,
            status=RequestStatus.new,
        )
        db.add(request)
        db.flush()

    for line in lines:
        qty = Decimal(str(line.qty_requested))
        db.add(
            RequestLine(
                request_id=request.id,
                item_id=line.item_id,
                qty_requested=qty,
                comment=line.comment or None,
            )
        )
        add_or_update_demand_line(db, branch.id, line.item_id, qty)

    request.status = RequestStatus.processed
    db.commit()
    db.refresh(request)
    return request
