"""Shared helpers used across admin sub-modules."""

import csv
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from urllib.parse import quote

from fastapi import Depends
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.database import get_db
from app.models import (
    AuditLog,
    DeliveryResultStatus,
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

logger = logging.getLogger(__name__)


def _money(value: object) -> float:
    return round(float(value or 0), 2)


def _parse_date(raw: str | None, default: datetime | None = None) -> datetime | None:
    if not raw:
        return default
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d")
    except ValueError:
        return default


def _clean_filter(raw: str | None, limit: int = 120) -> str:
    return (raw or "").strip()[:limit]


def _filter_variants(raw: str) -> list[str]:
    clean = raw.strip()
    variants = {
        clean,
        clean.lower(),
        clean.upper(),
        clean.capitalize(),
        clean.title(),
        clean.replace("ё", "е"),
        clean.replace("е", "ё"),
    }
    return [value for value in variants if value]


def _text_contains(column: object, raw: str):
    return or_(
        *[
            func.coalesce(column, "").like(f"%{variant}%")
            for variant in _filter_variants(raw)
        ]
    )


def _numeric_filter(raw: str) -> int | None:
    clean = raw.strip().lstrip("#№").strip()
    if clean.isdigit():
        return int(clean)
    return None


def _csv_response(filename: str, rows: list[dict[str, object]]) -> StreamingResponse:
    output = StringIO()
    fieldnames = list(rows[0].keys()) if rows else ["empty"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv; charset=utf-8", headers=headers)


def _xlsx_response(filename: str, buf: BytesIO) -> StreamingResponse:
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


def _active_admins(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User).where(
                User.role == UserRole.admin,
                User.is_active.is_(True),
                User.is_deleted.is_(False),
            )
        ).all()
    )


def _super_admin_error(current_user: User) -> RedirectResponse | None:
    if current_user.is_super_admin:
        return None
    return RedirectResponse(
        f"/admin?error={quote('Действие доступно только суперадмину')}#super",
        status_code=303,
    )


def _audit(
    db: Session,
    actor: User,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    details: str | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        )
    )


def _parse_decimal(raw: object, field_name: str) -> Decimal:
    try:
        value = Decimal(str(raw or "0").replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"{field_name} должно быть числом.") from None
    if value <= 0:
        raise ValueError(f"{field_name} должно быть больше 0.")
    return value


def _parse_non_negative_decimal(raw: object, field_name: str) -> Decimal:
    try:
        value = Decimal(str(raw or "0").replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"{field_name} должно быть числом.") from None
    if value < 0:
        raise ValueError(f"{field_name} не может быть меньше 0.")
    return value


def _validate_admin_password(password: str) -> str | None:
    if not password:
        return "Укажите пароль."
    if len(password) < 8:
        return "Пароль должен быть не короче 8 символов."
    return None


def _request_has_delivery(db: Session, request: GoodsRequest) -> bool:
    item_ids = [line.item_id for line in request.lines]
    if not item_ids:
        return False
    return (
        db.scalar(
            select(DeliverySessionLine.id)
            .join(DeliverySession)
            .where(
                DeliverySession.branch_id == request.branch_id,
                DeliverySessionLine.item_id.in_(item_ids),
                DeliverySession.is_deleted.is_(False),
            )
            .limit(1)
        )
        is not None
    )


def _result_status(qty_delivered: Decimal, qty_after: Decimal) -> DeliveryResultStatus:
    if qty_delivered == 0:
        return DeliveryResultStatus.none
    if qty_after > 0:
        return DeliveryResultStatus.partial
    return DeliveryResultStatus.full
