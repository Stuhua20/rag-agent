from typing import TypedDict


class KnowledgeQAState(TypedDict, total=False):
    run_id: str
    conversation_id: str
    workflow_version: str
    original_question: str
    resolved_question: str
    document_scope: dict
    scope_revision: int
    allowed_document_ids: list[str]
    conversation_context: str
    query_plan: dict
    requirements: list[dict]
    coverage: list[dict]
    sources: list[dict]
    pending_steps: list[dict]
    executed_actions: list[str]
    round: int
    no_growth: int
    retrieval_state: dict
    evidence_report: dict
    verifier_report: dict
    final_answer: str
    stop_reason: str
    status: str
    quality: dict
    halted: bool
