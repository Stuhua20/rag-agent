from langgraph.graph import END, StateGraph

from app.agents.knowledge_qa import nodes
from app.agents.knowledge_qa.runtime import RunContext
from app.agents.knowledge_qa.state import KnowledgeQAState
from app.core.config import settings


def after_assess(state: KnowledgeQAState) -> str:
    if state.get("halted"):
        return failure_node(state)
    if state["evidence_report"]["passed"]:
        return "generate"
    if (state["round"] >= settings.agent_max_rounds or state["no_growth"] >= 2
            or (state["retrieval_state"].get("full_scan_required")
                and not state["retrieval_state"].get("full_scan_complete"))):
        return "fallback"
    return "replan"


def failure_node(state: KnowledgeQAState) -> str:
    return "review_fallback" if state.get("review_mode") == "real" and state.get("halted") else "fallback"


def after_verify(state: KnowledgeQAState) -> str:
    if state.get("halted"):
        return failure_node(state)
    if state.get("review_mode") != "real":
        return "finalize"
    if state["verifier_report"]["passed"]:
        return "evidence_review"
    return repair_or_stop(state)


def repair_or_stop(state: KnowledgeQAState) -> str:
    return "repair" if state.get("revision_round", 0) < settings.evidence_review_max_revisions else "review_fallback"


def after_review(state: KnowledgeQAState) -> str:
    if state.get("halted") or state["review_report"]["passed"] is None:
        return "review_fallback"
    return "finalize" if state["review_report"]["passed"] else repair_or_stop(state)


def build_graph(checkpointer):
    graph = StateGraph(KnowledgeQAState, context_schema=RunContext)
    for name in nodes.LABELS:
        graph.add_node(name, nodes.guarded(getattr(nodes, name)))
    graph.set_entry_point("understand")
    graph.add_conditional_edges("understand", lambda state: failure_node(state) if state.get("halted") else (
        "clarify" if state["query_plan"].get("needs_clarification") else "execute"
    ), ["fallback", "review_fallback", "clarify", "execute"])
    graph.add_conditional_edges("execute", lambda state: failure_node(state) if state.get("halted") else "assess", ["fallback", "review_fallback", "assess"])
    graph.add_conditional_edges("assess", after_assess, ["fallback", "review_fallback", "generate", "replan"])
    graph.add_conditional_edges("replan", lambda state: failure_node(state) if state.get("halted") or not state["pending_steps"] else "execute", ["fallback", "review_fallback", "execute"])
    graph.add_conditional_edges("generate", lambda state: failure_node(state) if state.get("halted") else "verify", ["fallback", "review_fallback", "verify"])
    graph.add_conditional_edges("verify", after_verify, ["fallback", "review_fallback", "finalize", "evidence_review", "repair"])
    graph.add_conditional_edges("evidence_review", after_review, ["finalize", "repair", "review_fallback"])
    graph.add_conditional_edges("repair", lambda state: "review_fallback" if state.get("halted") or state.get("status") == "review_unavailable" else "verify", ["review_fallback", "verify"])
    graph.add_edge("clarify", "finalize")
    graph.add_edge("fallback", "finalize")
    graph.add_edge("review_fallback", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer, name="knowledge_qa")
