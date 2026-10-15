import json

from fastapi import APIRouter
from starlette.responses import StreamingResponse

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import chat_service


router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> dict:
    conversation = chat_service.prepare_conversation(
        request.conversation_id, request.question, request.expected_scope_revision,
    )
    return chat_service.ask(
        question=request.question,
        conversation_id=request.conversation_id,
        top_k=request.top_k,
        filters=request.filters,
        _conversation=conversation,
    )


def _sse_format(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream")
def chat_stream(request: ChatRequest):
    # Validate before sending SSE headers; invalid scopes must not start a run.
    conversation = chat_service.prepare_conversation(
        request.conversation_id, request.question, request.expected_scope_revision,
    )
    def generate():
        try:
            for chunk in chat_service.ask_stream(
                question=request.question,
                conversation_id=request.conversation_id,
                top_k=request.top_k,
                filters=request.filters,
                _conversation=conversation,
            ):
                yield _sse_format(chunk["event"], chunk["data"])
        except Exception as exc:
            yield _sse_format("error", {"message": str(exc)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
