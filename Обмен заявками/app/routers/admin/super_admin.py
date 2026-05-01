"""Super admin actions: restore, purge, recalculate, cleanup, backup, toggle super."""

import logging
from datetime import timedelta
from urllib.parse import quote

from fastapi import Depends, Form
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_roles
from app.database import DATABASE_PATH, DATABASE_URL, get_db
from app.models import (
    DeliverySession,
    DeliverySessionStatus,
    Request as GoodsRequest,
    User,
    UserRole,
    utc_now,
)
from app.routers.admin import router
from app.routers.admin._helpers import _audit, _parse_date, _super_admin_error
from app.routers.admin.demand import _recalculate_all_demand

logger = logging.getLogger(__name__)


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
    logger.info("Request #%d restored by super admin %d", request_id, current_user.id)
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
    logger.info("Delivery session #%d restored by super admin %d", session_id, current_user.id)
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
    logger.info(
        "Cleanup by super admin %d: requests=%d, sessions=%d",
        current_user.id, len(requests), len(sessions),
    )
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
    logger.info("Database backup downloaded by super admin %d", current_user.id)
    return FileResponse(
        DATABASE_PATH,
        media_type="application/octet-stream",
        filename=filename,
    )
