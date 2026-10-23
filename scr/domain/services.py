from __future__ import annotations

from typing import Any

SCORE_WEIGHTS = {"market_demand": 0.30, "competition": 0.25, "profitability": 0.20, "trend": 0.15, "supply_chain": 0.10}


def calculate_profit(
    selling_price: float = 29.99,
    cost_price: float = 8.50,
    weight_lb: float = 1.5,
    length_in: float = 10.0,
    width_in: float = 7.0,
    height_in: float = 5.0,
    shipping: float = 1.20,
    tax_rate: float = 0.05,
    size_tier: str = "large_standard",
    currency: str = "USD",
) -> dict[str, Any]:
    values = (selling_price, cost_price, weight_lb, length_in, width_in, height_in, shipping, tax_rate)
    if any(value < 0 for value in values) or selling_price <= 0:
        raise ValueError("售价必须大于 0，其余测算参数不能为负数")
    fees = {
        "small_standard": (3.50, 0.45, 0.50),
        "large_standard": (4.75, 0.60, 0.75),
        "large_oversize": (8.50, 1.20, 1.50),
    }
    if size_tier not in fees:
        raise ValueError("尺寸档位需为 small_standard、large_standard 或 large_oversize")
    if currency != "USD":
        raise ValueError("当前简化费率仅支持 USD；非美国站测算需要对应站点的费率表")
    pick_pack, weight_handling, monthly_storage = fees[size_tier]
    referral = round(max(selling_price * 0.15, 0.30), 2)
    fulfillment = round(pick_pack + weight_lb * weight_handling, 2)
    storage = round((length_in * width_in * height_in / 1728.0) * monthly_storage, 2)
    duty = round(cost_price * tax_rate, 2)
    total = round(referral + fulfillment + storage + shipping + duty, 2)
    net = round(selling_price - cost_price - total, 2)
    return {
        "selling_price": round(selling_price, 2), "cost_price": round(cost_price, 2),
        "referral_fee": round(referral, 2), "fba_fulfillment": round(fulfillment, 2),
        "storage_fee": round(storage, 2), "shipping": round(shipping, 2),
        "import_duty": round(duty, 2), "total_fees": round(total, 2),
        "net_profit": net, "profit_margin": round(net / selling_price * 100, 2),
        "size_tier": size_tier, "currency": currency,
    }


def calculate_score(scores: dict[str, float | None]) -> dict[str, Any]:
    normalized = {
        key: max(0.0, min(100.0, float(scores[key]))) if scores.get(key) is not None else None
        for key in SCORE_WEIGHTS
    }
    missing = [key for key, score in normalized.items() if score is None]
    coverage = round((len(SCORE_WEIGHTS) - len(missing)) / len(SCORE_WEIGHTS) * 100, 2)
    if missing:
        overall, grade, action = None, "待评估", "证据不足"
    else:
        overall = round(sum(normalized[key] * weight for key, weight in SCORE_WEIGHTS.items()), 2)
        grade = "A" if overall >= 80 else "B" if overall >= 65 else "C" if overall >= 50 else "D"
        action = "go" if overall >= 65 else "caution" if overall >= 50 else "abandon"
    return {
        "overall_score": overall,
        "grade": grade,
        "recommendation": action,
        "score_breakdown": normalized,
        "weights": SCORE_WEIGHTS,
        "score_coverage": coverage,
        "missing_dimensions": missing,
    }


def keyword_competition(keyword: str) -> str:
    count = len(keyword.split())
    return "low" if count >= 5 else "medium" if count >= 3 else "high"


def group_keywords(keywords: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "core": [item for item in keywords if not item.get("is_long_tail")],
        "long_tail": [item for item in keywords if item.get("is_long_tail")],
        "low_competition": [item for item in keywords if item.get("competition_level") == "low"],
    }
