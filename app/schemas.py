from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    user_id: str | None = Field(default=None, description="模拟用户 ID，例如 U1001")
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    intent: str
    answer: str
    need_tool: bool = False
    need_human: bool = False
    sources: list[str] = []
    confidence: float = Field(ge=0, le=1)


class HealthResponse(BaseModel):
    status: str
    project: str
    mode: str

