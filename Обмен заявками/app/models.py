from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class UserRole(StrEnum):
    appraiser = "appraiser"
    driver = "driver"
    admin = "admin"


class RequestStatus(StrEnum):
    new = "new"
    processed = "processed"
    closed = "closed"


class DemandStatus(StrEnum):
    active = "active"
    partially_delivered = "partially_delivered"
    delivered = "delivered"
    cancelled = "cancelled"


class DeliverySessionStatus(StrEnum):
    open = "open"
    closed = "closed"


class DeliveryResultStatus(StrEnum):
    full = "full"
    partial = "partial"
    none = "none"


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="branch")
    requests: Mapped[list["Request"]] = relationship(back_populates="branch")
    demand_lines: Mapped[list["DemandLine"]] = relationship(back_populates="branch")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    login: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    branch: Mapped[Branch | None] = relationship(back_populates="users")
    requests: Mapped[list["Request"]] = relationship(back_populates="created_by")
    delivery_sessions: Mapped[list["DeliverySession"]] = relationship(back_populates="driver")


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    unit_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    request_lines: Mapped[list["RequestLine"]] = relationship(back_populates="item")
    demand_lines: Mapped[list["DemandLine"]] = relationship(back_populates="item")


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus), default=RequestStatus.new, nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    branch: Mapped[Branch] = relationship(back_populates="requests")
    created_by: Mapped[User] = relationship(back_populates="requests")
    lines: Mapped[list["RequestLine"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class RequestLine(Base):
    __tablename__ = "request_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    qty_requested: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    request: Mapped[Request] = relationship(back_populates="lines")
    item: Mapped[Item] = relationship(back_populates="request_lines")


class DemandLine(Base):
    __tablename__ = "demand_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    qty_total_requested: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    qty_total_delivered: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    qty_remaining: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    status: Mapped[DemandStatus] = mapped_column(
        Enum(DemandStatus), default=DemandStatus.active, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    branch: Mapped[Branch] = relationship(back_populates="demand_lines")
    item: Mapped[Item] = relationship(back_populates="demand_lines")
    delivery_lines: Mapped[list["DeliverySessionLine"]] = relationship(back_populates="demand_line")


class DeliverySession(Base):
    __tablename__ = "delivery_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[DeliverySessionStatus] = mapped_column(
        Enum(DeliverySessionStatus), default=DeliverySessionStatus.open, nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    driver: Mapped[User] = relationship(back_populates="delivery_sessions")
    branch: Mapped[Branch] = relationship()
    lines: Mapped[list["DeliverySessionLine"]] = relationship(
        back_populates="delivery_session", cascade="all, delete-orphan"
    )


class DeliverySessionLine(Base):
    __tablename__ = "delivery_session_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    delivery_session_id: Mapped[int] = mapped_column(
        ForeignKey("delivery_sessions.id"), nullable=False
    )
    demand_line_id: Mapped[int] = mapped_column(ForeignKey("demand_lines.id"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    qty_before: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    qty_delivered_now: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    qty_after: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    result_status: Mapped[DeliveryResultStatus] = mapped_column(
        Enum(DeliveryResultStatus), nullable=False
    )

    delivery_session: Mapped[DeliverySession] = relationship(back_populates="lines")
    demand_line: Mapped[DemandLine] = relationship(back_populates="delivery_lines")
    item: Mapped[Item] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    actor: Mapped[User | None] = relationship()
