from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    question: str = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=50)
    filters: dict[str, Any] | None = None
    expected_scope_revision: int | None = Field(default=None, ge=0)


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    sources: list[dict[str, Any]]
    quality: dict[str, Any]
