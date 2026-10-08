from enum import Enum


class Intent(str, Enum):
    ORDER = "订单查询"
    SHIPMENT = "物流查询"
    REFUND = "退款申请"
    RETURN_POLICY = "退货政策咨询"
    PRODUCT = "商品咨询"
    OTHER = "其他"


def classify(message: str) -> Intent:
    lowered = message.lower()
    if any(keyword in lowered for keyword in ["退款", "退钱", "退货申请"]):
        return Intent.REFUND
    if any(keyword in lowered for keyword in ["物流", "包裹", "到哪里", "什么时候到"]):
        return Intent.SHIPMENT
    if "订单" in lowered or "bc" in lowered:
        return Intent.ORDER
    if any(keyword in lowered for keyword in ["退货政策", "退货", "退换"]):
        return Intent.RETURN_POLICY
    if any(keyword in lowered for keyword in ["商品", "产品", "sku", "价格"]):
        return Intent.PRODUCT
    return Intent.OTHER

