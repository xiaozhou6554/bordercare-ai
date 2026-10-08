from app.application.chat_use_case import ChatUseCase
from app.infrastructure.persistence.sqlite_order_repository import SqliteOrderRepository
from app.schemas import ChatRequest, ChatResponse


def chat(request: ChatRequest) -> ChatResponse:
    """Backward-compatible facade; new code should call ChatUseCase directly."""
    return ChatUseCase(SqliteOrderRepository()).execute(request)
