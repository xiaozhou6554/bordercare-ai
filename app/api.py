from fastapi import FastAPI

from app.chat_service import chat
from app.config import PROJECT_NAME, SIMULATION_MODE
from app.database import initialize_database
from app.schemas import ChatRequest, ChatResponse, HealthResponse


app = FastAPI(
    title=PROJECT_NAME,
    description="跨境电商智能客服与运营助手的本地模拟 API",
    version="0.1.0",
)


@app.on_event("startup")
def startup() -> None:
    initialize_database()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        project=PROJECT_NAME,
        mode="simulation" if SIMULATION_MODE else "production",
    )


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest) -> ChatResponse:
    return chat(request)

