from fastapi import APIRouter

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import chat_service


router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> dict:
    return chat_service.ask(
        question=request.question,
        conversation_id=request.conversation_id,
        top_k=request.top_k,
        filters=request.filters,
    )
