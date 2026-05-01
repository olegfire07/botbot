"""History: update/delete/restore requests and delivery sessions."""

import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_roles
from app.database import get_db
from app.models import (
    DeliveryResultStatus,
    DeliverySession,
    DeliverySessionLine,
    DeliverySessionStatus,
    Request as GoodsRequest,
    RequestLine,
    RequestStatus,
    User,
    UserRole,
    utc_now,
)
from app.routers.admin import router
from app.routers.admin._helpers import (
    _audit,
    _parse_decimal,
    _parse_non_negative_decimal,
    _result_status,
    _super_admin_error,
)
from app.routers.admin.demand import (
    _recalculate_all_demand,
    recalculate_demand_for_keys,
)

logger = logging.getLogger(__name__)


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

    # Collect affected (branch_id, item_id) keys for incremental recalculation
    affected_keys: set[tuple[int, int]] = set()
    try:
        for line_id_raw, qty_raw, comment_raw in zip(line_ids, qty_values, comments, strict=False):
            line_id = int(line_id_raw)
            line = lines_by_id.get(line_id)
            if not line:
                raise ValueError("Строка заявки не найдена.")
            affected_keys.add((goods_request.branch_id, line.item_id))
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
    recalculate_demand_for_keys(db, affected_keys)
    _audit(db, current_user, "update", "request", request_id, "Заявка обновлена")
    db.commit()
    logger.info("Request #%d updated by user %d", request_id, current_user.id)
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
        affected_keys = {
            (goods_request.branch_id, line.item_id) for line in goods_request.lines
        }
        goods_request.is_deleted = True
        recalculate_demand_for_keys(db, affected_keys)
        _audit(db, current_user, "soft_delete", "request", request_id, "Заявка удалена из истории")
        db.commit()
    except ValueError as exc:
        db.rollback()
        return RedirectResponse(
            f"/admin?error={quote(str(exc))}#history", status_code=303
        )
    logger.info("Request #%d deleted by user %d", request_id, current_user.id)
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
    reason_values = form.getlist("shortage_reason")
    lines_by_id = {line.id: line for line in session.lines}

    affected_keys: set[tuple[int, int]] = set()
    try:
        for index, (line_id_raw, qty_raw) in enumerate(zip(line_ids, qty_values, strict=False)):
            line_id = int(line_id_raw)
            line = lines_by_id.get(line_id)
            if not line:
                raise ValueError("Строка визита не найдена.")
            affected_keys.add((session.branch_id, line.item_id))
            qty = _parse_non_negative_decimal(qty_raw, "Доставлено")
            qty_before = Decimal(line.qty_before)
            if qty > qty_before:
                raise ValueError("Нельзя доставить больше остатка в строке визита.")
            line.qty_delivered_now = qty
            line.qty_after = qty_before - qty
            line.result_status = _result_status(qty, Decimal(line.qty_after))
            shortage_reason = str(reason_values[index] if index < len(reason_values) else "").strip()
            if len(shortage_reason) > 500:
                raise ValueError("Причина недовоза не должна быть длиннее 500 символов.")
            line.shortage_reason = (
                shortage_reason if line.result_status != DeliveryResultStatus.full else None
            )
    except (ValueError, InvalidOperation) as exc:
        db.rollback()
        return RedirectResponse(
            f"/admin?error={quote(str(exc))}#history", status_code=303
        )

    recalculate_demand_for_keys(db, affected_keys)
    _audit(db, current_user, "update", "delivery_session", session_id, "Визит обновлён")
    db.commit()
    logger.info("Delivery session #%d updated by user %d", session_id, current_user.id)
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
        affected_keys = {
            (session.branch_id, line.item_id) for line in session.lines
        }
        session.is_deleted = True
        session.status = DeliverySessionStatus.closed
        session.finished_at = session.finished_at or utc_now()
        recalculate_demand_for_keys(db, affected_keys)
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
    logger.info("Delivery session #%d deleted by user %d", session_id, current_user.id)
    return RedirectResponse(
        f"/admin?message={quote('Визит удалён из истории и отчётов')}#history", status_code=303
    )


@router.get("/delivery-sessions/{session_id}/delete")
def delete_delivery_session_get_fallback(session_id: int):
    return RedirectResponse(
        f"/admin?error={quote('Удаление выполняется только кнопкой формы. Обновите страницу и нажмите «Удалить» ещё раз.')}#history",
        status_code=303,
    )
