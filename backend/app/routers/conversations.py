from fastapi import APIRouter, HTTPException

from app.schemas.conversation import CreateConversationRequest, RenameConversationRequest, UpdateConversationRequest
from app.services.chat_service import chat_service


router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
def list_conversations() -> list[dict]:
    return chat_service.list_conversations()


@router.post("")
def create_conversation(request: CreateConversationRequest | None = None) -> dict:
    return chat_service.create_conversation(
        request.title if request else None, request.document_scope.model_dump() if request else None,
    )


@router.get("/{conversation_id}")
def get_conversation(conversation_id: str) -> dict:
    return chat_service.get_conversation(conversation_id)


@router.patch("/{conversation_id}")
def update_conversation(conversation_id: str, request: UpdateConversationRequest) -> dict:
    return chat_service.update_document_scope(
        conversation_id, request.document_scope.model_dump(), request.expected_scope_revision,
    )


@router.get("/{conversation_id}/messages")
def list_messages(conversation_id: str) -> list[dict]:
    return chat_service.list_messages(conversation_id)


@router.patch("/{conversation_id}/title")
def rename_conversation(conversation_id: str, request: RenameConversationRequest) -> dict:
    return chat_service.rename_conversation(conversation_id, request.title)


@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict:
    deleted = chat_service.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True}
