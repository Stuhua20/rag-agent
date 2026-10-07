from typing import Literal

from pydantic import BaseModel, Field


class EmbeddingSettingsPayload(BaseModel):
    provider: str | None = Field(default=None, min_length=1)
    base_url: str | None = Field(default=None, min_length=1)
    model: str | None = Field(default=None, min_length=1)
    mock: bool | None = None
    normalize: bool | None = None


class LlmSettingsPayload(BaseModel):
    provider: str | None = Field(default=None, min_length=1)
    base_url: str | None = Field(default=None, min_length=1)
    model: str | None = Field(default=None, min_length=1)
    mock: bool | None = None


class RetrievalSettingsPayload(BaseModel):
    top_k: int | None = Field(default=None, ge=1, le=50)
    chunk_size: int | None = Field(default=None, ge=1, le=100_000)
    overlap: int | None = Field(default=None, ge=0, le=100_000)
    score_threshold: float | None = Field(default=None, ge=0, le=1)
    search_mode: Literal["hybrid", "vector", "keyword"] | None = None
    max_chunks_per_doc: int | None = Field(default=None, ge=0, le=1_000)
    full_scan_max_chunks: int | None = Field(default=None, ge=1, le=10_000)


class ConversationSettingsPayload(BaseModel):
    context_window: int | None = Field(default=None, ge=0, le=50)


class SecretSettingsPayload(BaseModel):
    embedding_api_key: str | None = None
    llm_api_key: str | None = None


class SettingsPayload(BaseModel):
    embedding: EmbeddingSettingsPayload | None = None
    llm: LlmSettingsPayload | None = None
    retrieval: RetrievalSettingsPayload | None = None
    conversation: ConversationSettingsPayload | None = None
    secrets: SecretSettingsPayload | None = None
