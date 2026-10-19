from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DocumentScope(BaseModel):
    mode: Literal["all", "selected"] = "all"
    document_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_selection(self) -> "DocumentScope":
        self.document_ids = sorted(set(self.document_ids))
        if self.mode == "selected" and (not self.document_ids or any(not value.strip() for value in self.document_ids)):
            raise ValueError("指定文档模式至少需要选择一个有效文档。")
        if self.mode == "all" and self.document_ids:
            raise ValueError("全部文档模式不能携带指定文档。")
        return self


class CreateConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    document_scope: DocumentScope = Field(default_factory=DocumentScope)


class UpdateConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_scope: DocumentScope
    expected_scope_revision: int = Field(ge=0)


class RenameConversationRequest(BaseModel):
    title: str = Field(strict=True)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        title = value.strip()
        if not 1 <= len(title) <= 100:
            raise ValueError("聊天名称去除首尾空白后须为 1–100 个字符。")
        return title
