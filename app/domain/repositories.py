from typing import Protocol

from app.domain.entities import Order, Shipment


class OrderRepository(Protocol):
    def find_order(self, order_id: str) -> Order | None:
        """Return one order without deciding whether the caller may view it."""

    def find_shipment(self, order_id: str) -> Shipment | None:
        """Return shipment data for an order."""

    def record_audit(self, user_id: str | None, action: str, detail: str) -> None:
        """Record an auditable business action."""

