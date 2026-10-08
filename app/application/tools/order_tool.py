import re

from app.domain.repositories import OrderRepository
from app.domain.services import OrderAccessPolicy


ORDER_PATTERN = re.compile(r"\bBC\d{5}\b", re.IGNORECASE)


class OrderTool:
    """Read-only customer order tool exposed to the Agent."""

    def __init__(self, repository: OrderRepository) -> None:
        self.repository = repository

    def extract_order_id(self, message: str) -> str | None:
        match = ORDER_PATTERN.search(message)
        return match.group(0).upper() if match else None

    def query(self, message: str, user_id: str | None, shipment_only: bool) -> dict:
        order_id = self.extract_order_id(message)
        if not order_id:
            return {"status": "missing_order_id"}
        if not user_id:
            return {"status": "missing_user_id"}

        order = self.repository.find_order(order_id)
        if order is None:
            return {"status": "not_found", "order_id": order_id}
        if not OrderAccessPolicy.can_view(order, user_id):
            self.repository.record_audit(user_id, "access_denied", f"order={order_id}")
            return {"status": "access_denied", "order_id": order_id}

        self.repository.record_audit(user_id, "query_order", f"order={order_id}")
        if shipment_only:
            shipment = self.repository.find_shipment(order_id)
            return {"status": "ok", "order": order, "shipment": shipment}
        return {"status": "ok", "order": order}

