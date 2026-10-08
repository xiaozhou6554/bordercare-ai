from app.application.agents.router import Intent, classify
from app.application.tools.order_tool import OrderTool
from app.schemas import ChatRequest, ChatResponse


class CustomerAgent:
    """Deterministic Agent: route first, then call a bounded tool or policy service."""

    def __init__(self, order_tool: OrderTool) -> None:
        self.order_tool = order_tool

    def handle(self, request: ChatRequest) -> ChatResponse:
        intent = classify(request.message)

        if intent in (Intent.ORDER, Intent.SHIPMENT):
            return self._handle_order(request, intent)
        if intent == Intent.REFUND:
            return ChatResponse(
                intent=intent,
                answer="退款或退货申请属于高风险操作，当前模板只创建申请草稿，后续需要用户确认并由客服审核。",
                need_human=True,
                confidence=0.96,
            )
        if intent == Intent.RETURN_POLICY:
            return ChatResponse(
                intent=intent,
                answer="这是模拟店铺政策。请先确认所在市场；当前模板支持美国、英国和德国政策文档，后续会通过 RAG 返回带引用的答案。",
                sources=["data/raw/policies/return_policy_us.md", "data/raw/policies/return_policy_de.md"],
                confidence=0.82,
            )
        if intent == Intent.PRODUCT:
            return ChatResponse(
                intent=intent,
                answer="当前模板已准备商品数据，下一步会增加 SKU 精确匹配和商品知识库检索。",
                sources=["data/raw/products/products.csv"],
                confidence=0.78,
            )
        return ChatResponse(
            intent=intent,
            answer="我还不能确定你的问题类型。你可以试试询问订单、物流、商品或退货政策。",
            confidence=0.55,
        )

    def _handle_order(self, request: ChatRequest, intent: Intent) -> ChatResponse:
        result = self.order_tool.query(
            request.message,
            request.user_id,
            shipment_only=intent == Intent.SHIPMENT,
        )
        if result["status"] == "missing_order_id":
            return ChatResponse(intent=intent, answer="请提供订单号，例如 BC10001，我再帮你查询。", need_tool=True, confidence=0.88)
        if result["status"] == "missing_user_id":
            return ChatResponse(intent=intent, answer="为了保护订单信息，请先提供模拟用户 ID。", need_tool=True, confidence=0.95)
        if result["status"] == "not_found":
            return ChatResponse(intent=intent, answer=f"暂时没有找到订单 {result['order_id']}。请检查订单号是否正确。", need_tool=True, confidence=0.94)
        if result["status"] == "access_denied":
            return ChatResponse(intent=intent, answer="抱歉，你没有权限查询这个订单。", need_tool=True, confidence=0.99)

        order = result["order"]
        if intent == Intent.SHIPMENT:
            shipment = result["shipment"]
            answer = f"订单 {order.order_id} 当前物流状态为“{shipment.status}”，承运商：{shipment.carrier}，最新信息：{shipment.last_event}。"
        else:
            answer = f"订单 {order.order_id} 当前状态为“{order.status}”，金额为 {order.currency} {order.total_amount:.2f}。"
        return ChatResponse(intent=intent, answer=answer, need_tool=True, sources=["模拟订单数据库"], confidence=0.97)

