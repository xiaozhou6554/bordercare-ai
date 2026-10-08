from fastapi.testclient import TestClient

from app.api import app
from scripts.seed_db import seed


seed()
client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_missing_order_id() -> None:
    response = client.post(
        "/chat",
        json={"user_id": "U1001", "message": "帮我查一下订单"},
    )
    assert response.status_code == 200
    assert response.json()["intent"] == "订单查询"
    assert "订单号" in response.json()["answer"]


def test_order_access_control() -> None:
    response = client.post(
        "/chat",
        json={"user_id": "U1002", "message": "查询订单 BC10001"},
    )
    assert response.status_code == 200
    assert "没有权限" in response.json()["answer"]
