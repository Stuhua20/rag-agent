from typing import Any

from pydantic import BaseModel


class UploadResponse(BaseModel):
    document_id: str
    status: str
    sheet_count: int
    chunk_count: int


class ChunkPage(BaseModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int

