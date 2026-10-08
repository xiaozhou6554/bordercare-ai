from app.application.agents.customer_agent import CustomerAgent
from app.application.tools.order_tool import OrderTool
from app.domain.repositories import OrderRepository
from app.schemas import ChatRequest, ChatResponse


class ChatUseCase:
    """Application use case. It wires the Agent to ports without knowing SQLite details."""

    def __init__(self, repository: OrderRepository) -> None:
        self.agent = CustomerAgent(OrderTool(repository))

    def execute(self, request: ChatRequest) -> ChatResponse:
        return self.agent.handle(request)

