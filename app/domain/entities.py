from dataclasses import dataclass


@dataclass(frozen=True)
class Order:
    order_id: str
    user_id: str
    market: str
    currency: str
    total_amount: float
    status: str


@dataclass(frozen=True)
class Shipment:
    order_id: str
    carrier: str
    status: str
    last_event: str

