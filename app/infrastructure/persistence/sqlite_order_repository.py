from datetime import datetime

from app.database import get_connection
from app.domain.entities import Order, Shipment


class SqliteOrderRepository:
    """SQLite adapter. Application and domain layers do not depend on SQL details."""

    def find_order(self, order_id: str) -> Order | None:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT order_id, user_id, market, currency, total_amount, status "
                "FROM orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
        if row is None:
            return None
        return Order(
            order_id=row["order_id"],
            user_id=row["user_id"],
            market=row["market"],
            currency=row["currency"],
            total_amount=row["total_amount"],
            status=row["status"],
        )

    def find_shipment(self, order_id: str) -> Shipment | None:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT order_id, carrier, status, last_event "
                "FROM shipments WHERE order_id = ?",
                (order_id,),
            ).fetchone()
        if row is None:
            return None
        return Shipment(
            order_id=row["order_id"],
            carrier=row["carrier"],
            status=row["status"],
            last_event=row["last_event"],
        )

    def record_audit(self, user_id: str | None, action: str, detail: str) -> None:
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO audit_logs(user_id, action, detail, created_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, action, detail, datetime.utcnow().isoformat()),
            )

