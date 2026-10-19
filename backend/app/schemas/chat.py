from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str | None = None
    question: str = Field(min_length=1, max_length=8000)
    top_k: int | None = Field(default=None, ge=1, le=50)
    filters: dict[str, Any] | None = None
    expected_scope_revision: int | None = Field(default=None, ge=0)

    @field_validator("question")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("请输入问题。")
        return value


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    sources: list[dict[str, Any]]
    quality: dict[str, Any]
    run_id: str | None = None
    status: str | None = None
