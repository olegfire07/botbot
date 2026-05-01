from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RequestLineInput:
    item_id: int
    qty_requested: float | Decimal
    comment: str | None = None


@dataclass(frozen=True)
class DeliveryLineInput:
    demand_line_id: int
    qty_delivered_now: float | Decimal
    shortage_reason: str | None = None
