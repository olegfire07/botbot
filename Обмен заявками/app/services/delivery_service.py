from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Branch,
    DeliveryResultStatus,
    DeliverySession,
    DeliverySessionLine,
    DeliverySessionStatus,
    DemandLine,
    DemandStatus,
    User,
    UserRole,
    utc_now,
)
from app.schemas import DeliveryLineInput
from app.services.demand_service import recalculate_demand_status


class DeliveryValidationError(ValueError):
    pass


from decimal import Decimal, InvalidOperation


def get_or_open_delivery_session(db: Session, driver_id: int, branch_id: int) -> DeliverySession:
    driver = db.get(User, driver_id)
    if not driver or driver.role != UserRole.driver or not driver.is_active or driver.is_deleted:
        raise DeliveryValidationError("Выберите водителя.")

    branch = db.get(Branch, branch_id)
    if not branch or not branch.is_active or branch.is_deleted:
        raise DeliveryValidationError("Выберите активное подразделение.")

    open_session = db.scalar(
        select(DeliverySession).where(
            DeliverySession.driver_id == driver_id,
            DeliverySession.status == DeliverySessionStatus.open,
            DeliverySession.is_deleted.is_(False),
        )
    )
    if open_session:
        return open_session

    session = DeliverySession(
        driver_id=driver_id,
        branch_id=branch_id,
        status=DeliverySessionStatus.open,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def save_delivery_result(
    db: Session,
    delivery_session_id: int,
    lines: list[DeliveryLineInput],
) -> DeliverySession:
    session = db.get(DeliverySession, delivery_session_id)
    if not session:
        raise DeliveryValidationError("Визит не найден.")
    if session.is_deleted:
        raise DeliveryValidationError("Визит удалён администратором.")
    if session.status == DeliverySessionStatus.closed:
        raise DeliveryValidationError("Закрытый визит нельзя редактировать.")

    seen_demand_lines: set[int] = set()
    for line in lines:
        if line.demand_line_id in seen_demand_lines:
            raise DeliveryValidationError("Одна позиция не может быть сохранена дважды в одном визите.")
        seen_demand_lines.add(line.demand_line_id)

    validated_lines = []
    for line in lines:
        demand_line = db.scalar(
            select(DemandLine).where(DemandLine.id == line.demand_line_id).with_for_update()
        )
        if not demand_line or demand_line.branch_id != session.branch_id:
            raise DeliveryValidationError("Позиция активной потребности не найдена.")
        existing_line = db.scalar(
            select(DeliverySessionLine).where(
                DeliverySessionLine.delivery_session_id == session.id,
                DeliverySessionLine.demand_line_id == demand_line.id,
            )
        )
        if existing_line:
            raise DeliveryValidationError(
                f"Позиция «{demand_line.item.name}» уже сохранена в этом визите."
            )
        if demand_line.status not in (DemandStatus.active, DemandStatus.partially_delivered):
            continue
        try:
            qty_delivered_now = Decimal(str(line.qty_delivered_now))
        except InvalidOperation:
            raise DeliveryValidationError("Количество доставки должно быть числом.")

        if qty_delivered_now < 0:
            raise DeliveryValidationError("Количество доставки не может быть меньше 0.")

        qty_before = demand_line.qty_remaining
        if qty_delivered_now > qty_before:
            raise DeliveryValidationError(
                f"Нельзя доставить больше остатка по позиции «{demand_line.item.name}»."
            )

        qty_after = qty_before - qty_delivered_now
        if qty_delivered_now == 0:
            result_status = DeliveryResultStatus.none
        elif qty_after > 0:
            result_status = DeliveryResultStatus.partial
        else:
            result_status = DeliveryResultStatus.full

        shortage_reason = (line.shortage_reason or "").strip()
        if len(shortage_reason) > 500:
            raise DeliveryValidationError("Причина недовоза не должна быть длиннее 500 символов.")
        if result_status == DeliveryResultStatus.full:
            shortage_reason = ""

        validated_lines.append(
            (demand_line, qty_before, qty_delivered_now, qty_after, result_status, shortage_reason)
        )

    for (
        demand_line,
        qty_before,
        qty_delivered_now,
        qty_after,
        result_status,
        shortage_reason,
    ) in validated_lines:
        db.add(
            DeliverySessionLine(
                delivery_session_id=session.id,
                demand_line_id=demand_line.id,
                item_id=demand_line.item_id,
                qty_before=qty_before,
                qty_delivered_now=qty_delivered_now,
                qty_after=qty_after,
                result_status=result_status,
                shortage_reason=shortage_reason or None,
            )
        )
        demand_line.qty_total_delivered = demand_line.qty_total_delivered + qty_delivered_now
        demand_line.qty_remaining = qty_after
        recalculate_demand_status(demand_line)

    db.commit()
    db.refresh(session)
    return session


def close_delivery_session(db: Session, delivery_session_id: int) -> DeliverySession:
    session = db.get(DeliverySession, delivery_session_id)
    if not session:
        raise DeliveryValidationError("Визит не найден.")
    if session.is_deleted:
        raise DeliveryValidationError("Визит удалён администратором.")
    if session.status != DeliverySessionStatus.closed:
        session.status = DeliverySessionStatus.closed
        session.finished_at = utc_now()
        db.commit()
        db.refresh(session)
    return session
