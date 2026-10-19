from langgraph.graph import END, StateGraph

from app.agents.knowledge_qa import nodes
from app.agents.knowledge_qa.runtime import RunContext
from app.agents.knowledge_qa.state import KnowledgeQAState
from app.core.config import settings


def after_assess(state: KnowledgeQAState) -> str:
    if state.get("halted"):
        return "fallback"
    if state["evidence_report"]["passed"]:
        return "generate"
    if (state["round"] >= settings.agent_max_rounds or state["no_growth"] >= 2
            or (state["retrieval_state"].get("full_scan_required")
                and not state["retrieval_state"].get("full_scan_complete"))):
        return "fallback"
    return "replan"


def build_graph(checkpointer):
    graph = StateGraph(KnowledgeQAState, context_schema=RunContext)
    for name in nodes.LABELS:
        graph.add_node(name, nodes.guarded(getattr(nodes, name)))
    graph.set_entry_point("understand")
    graph.add_conditional_edges("understand", lambda state: "fallback" if state.get("halted") else (
        "clarify" if state["query_plan"].get("needs_clarification") else "execute"
    ), ["fallback", "clarify", "execute"])
    graph.add_conditional_edges("execute", lambda state: "fallback" if state.get("halted") else "assess", ["fallback", "assess"])
    graph.add_conditional_edges("assess", after_assess, ["fallback", "generate", "replan"])
    graph.add_conditional_edges("replan", lambda state: "fallback" if state.get("halted") or not state["pending_steps"] else "execute", ["fallback", "execute"])
    graph.add_conditional_edges("generate", lambda state: "fallback" if state.get("halted") else "verify", ["fallback", "verify"])
    graph.add_conditional_edges("verify", lambda state: "fallback" if state.get("halted") else "finalize", ["fallback", "finalize"])
    graph.add_edge("clarify", "finalize")
    graph.add_edge("fallback", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer, name="knowledge_qa")
