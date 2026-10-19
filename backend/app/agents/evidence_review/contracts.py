from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AnswerUnit(Contract):
    id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=12000)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    structural: bool = False


class Requirement(Contract):
    id: str = Field(min_length=1, max_length=100)
    query: str = Field(min_length=1, max_length=2000)


class Evidence(Contract):
    id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=6000)
    file_name: str = Field(default="", max_length=500)


class ReviewInput(Contract):
    original_question: str = Field(min_length=1, max_length=8000)
    resolved_question: str = Field(min_length=1, max_length=8000)
    requirements: list[Requirement] = Field(min_length=1, max_length=6)
    answer_units: list[AnswerUnit] = Field(min_length=1, max_length=100)
    evidence: list[Evidence] = Field(min_length=1, max_length=20)
    rule_report: dict
    revision_round: int = Field(ge=0, le=1)


class EvidenceRef(Contract):
    evidence_id: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=6000)


Issue = Annotated[str, Field(min_length=1, max_length=2000)]


class UnitReview(Contract):
    unit_id: str = Field(min_length=1, max_length=100)
    status: Literal["supported", "contradicted", "unsupported", "uncertain", "non_factual"]
    evidence_refs: list[EvidenceRef] = Field(max_length=20)
    issues: list[Issue] = Field(max_length=8)


class TaskReview(Contract):
    requirement_id: str = Field(min_length=1, max_length=100)
    status: Literal["answered", "gap_disclosed", "omitted", "uncertain"]
    answer_unit_ids: list[str] = Field(max_length=100)
    reason: str = Field(max_length=2000)


class ReviewResult(Contract):
    units: list[UnitReview] = Field(min_length=1, max_length=100)
    tasks: list[TaskReview] = Field(min_length=1, max_length=6)
