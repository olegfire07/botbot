from dataclasses import dataclass


@dataclass(frozen=True)
class RequestLineInput:
    item_id: int
    qty_requested: float
    comment: str | None = None


@dataclass(frozen=True)
class DeliveryLineInput:
    demand_line_id: int
    qty_delivered_now: float
