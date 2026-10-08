from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_connection, reset_database  # noqa: E402


def seed() -> None:
    reset_database()
    with get_connection() as connection:
        connection.executemany(
            "INSERT INTO users(user_id, email, market, language) VALUES (?, ?, ?, ?)",
            [
                ("U1001", "alice@example.test", "US", "en"),
                ("U1002", "bernd@example.test", "DE", "de"),
                ("U1003", "charlie@example.test", "UK", "en"),
            ],
        )
        connection.executemany(
            "INSERT INTO products(sku, name, name_en, category, price_usd, active) VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("TRAVEL-CUBE-S", "旅行收纳袋 S 号", "Travel Packing Cube S", "travel", 12.90, 1),
                ("TRAVEL-CUBE-M", "旅行收纳袋 M 号", "Travel Packing Cube M", "travel", 16.90, 1),
                ("LAPTOP-SLEEVE-13", "13 英寸电脑包", "Laptop Sleeve 13 inch", "computer_accessories", 24.90, 1),
                ("CABLE-ORG-BLACK", "黑色数据线收纳包", "Cable Organizer Black", "accessories", 9.90, 1),
                ("PASSPORT-WALLET", "护照收纳夹", "Passport Wallet", "travel", 18.90, 1),
            ],
        )
        connection.executemany(
            "INSERT INTO inventory(sku, available_quantity, warning_threshold) VALUES (?, ?, ?)",
            [
                ("TRAVEL-CUBE-S", 42, 10),
                ("TRAVEL-CUBE-M", 8, 10),
                ("LAPTOP-SLEEVE-13", 25, 5),
                ("CABLE-ORG-BLACK", 0, 5),
                ("PASSPORT-WALLET", 17, 5),
            ],
        )
        connection.executemany(
            "INSERT INTO orders(order_id, user_id, market, currency, total_amount, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("BC10001", "U1001", "US", "USD", 38.70, "in_transit", "2026-10-01T09:30:00"),
                ("BC10002", "U1001", "US", "USD", 24.90, "delivered", "2026-09-20T13:10:00"),
                ("BC10003", "U1002", "DE", "EUR", 16.90, "processing", "2026-10-06T10:15:00"),
                ("BC10004", "U1003", "UK", "GBP", 18.90, "refund_requested", "2026-10-05T16:45:00"),
            ],
        )
        connection.executemany(
            "INSERT INTO order_items(order_id, sku, quantity, unit_price) VALUES (?, ?, ?, ?)",
            [
                ("BC10001", "TRAVEL-CUBE-S", 1, 12.90),
                ("BC10001", "TRAVEL-CUBE-M", 1, 16.90),
                ("BC10002", "LAPTOP-SLEEVE-13", 1, 24.90),
                ("BC10003", "TRAVEL-CUBE-M", 1, 16.90),
                ("BC10004", "PASSPORT-WALLET", 1, 18.90),
            ],
        )
        connection.executemany(
            "INSERT INTO shipments(shipment_id, order_id, carrier, tracking_number, status, estimated_delivery, last_event) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("SHP10001", "BC10001", "DHL", "DHL-DEMO-10001", "in_transit", "2026-10-10", "Package arrived at regional sorting center"),
                ("SHP10002", "BC10002", "UPS", "UPS-DEMO-10002", "delivered", "2026-09-26", "Delivered to front door"),
                ("SHP10003", "BC10003", "DHL", "DHL-DEMO-10003", "label_created", "2026-10-14", "Shipping label created"),
                ("SHP10004", "BC10004", "Royal Mail", "RM-DEMO-10004", "held_for_review", "2026-10-12", "Shipment held for customer service review"),
            ],
        )
    print("Seed completed: database/bordercare.db")


if __name__ == "__main__":
    seed()

