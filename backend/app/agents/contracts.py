from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceRequirement(BaseModel):
    id: str
    query: str = Field(min_length=1, max_length=2000)
    target: str = Field(default="", max_length=200)
    terms: list[str] = Field(default_factory=list, max_length=8)


class CoverageItem(BaseModel):
    requirement_id: str
    status: Literal["covered", "missing", "uncertain", "conflict"]
    evidence_ids: list[str] = Field(default_factory=list)
    quote: str = ""


class Replan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    queries: list[str] = Field(max_length=3)


class ToolStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal["search_knowledge", "read_evidence_context"]
    queries: list[str] = Field(default_factory=list, max_length=3)
    chunk_ids: list[str] = Field(default_factory=list, max_length=3)


class ToolResult(BaseModel):
    tool: str
    status: Literal["success", "empty"]
    sources: list[dict] = Field(default_factory=list)
    coverage: dict = Field(default_factory=dict)
