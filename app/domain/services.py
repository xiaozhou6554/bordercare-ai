from app.domain.entities import Order


class OrderAccessPolicy:
    """Domain rule: a customer can only view their own order."""

    @staticmethod
    def can_view(order: Order, user_id: str | None) -> bool:
        return bool(user_id) and order.user_id == user_id

