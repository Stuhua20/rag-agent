import json

from app.agents.contracts import ToolResult, ToolStep
from app.services.json_store_service import json_store
from app.services.query_understanding_service import query_understanding_service
from app.services.retrieval_service import retrieval_service


def action_key(step: ToolStep, document_ids: list[str]) -> str:
    return json.dumps([step.model_dump(), sorted(document_ids)], sort_keys=True, ensure_ascii=False)


def execute_tool(step: ToolStep, state: dict, context) -> ToolResult:
    context.check()
    context.budget.consume("tool")
    # User constraints and server-selected scope always override model filters.
    filters = {**(state["query_plan"].get("filters") or {}), **context.filters,
               "document_ids": state["allowed_document_ids"]}
    question = state["resolved_question"]
    if step.tool == "read_evidence_context":
        known_ids = {item["chunk_id"] for item in state.get("sources", [])}
        if not set(step.chunk_ids).issubset(known_ids):
            raise ValueError("只能读取本轮命中证据的相关片段。")
        chunks = json_store.list_items("chunks.json")
        ids = []
        for anchor in chunks:
            if anchor["id"] not in step.chunk_ids or anchor["document_id"] not in state["allowed_document_ids"]:
                continue
            siblings = sorted([
                item for item in chunks if item["document_id"] == anchor["document_id"]
                and item.get("sheet_id") == anchor.get("sheet_id")
                and isinstance(item.get("row_start"), int)
            ], key=lambda item: (item["row_start"], item["id"]))
            if anchor in siblings:
                index = siblings.index(anchor)
                ids.extend(item["id"] for item in siblings[max(0, index - 1):index + 2])
            else:
                ids.append(anchor["id"])
        sources = retrieval_service.sources_for_chunk_ids(list(dict.fromkeys(ids)), document_ids=state["allowed_document_ids"])
        sources = [item for item in sources if not filters.get("sheet_name") or item.get("sheet_name") == filters["sheet_name"]]
        # Context reads are evidence access, not a new exact semantic match.
        for source in sources:
            source["score_type"] = "similarity"
            source["score"] = 0.0
        return ToolResult(tool=step.tool, status="success" if sources else "empty", sources=sources)
    full_scan = query_understanding_service.needs_full_scan(question, state["query_plan"])
    sources = retrieval_service.search_multiple(
        step.queries, top_k=context.top_k or state["query_plan"].get("retrieval", {}).get("top_k") or retrieval_service.top_k(),
        filters=filters, full_scan=full_scan,
    )
    # Defend at the tool boundary even if an underlying adapter returns stale results.
    sources = [item for item in sources if item.get("document_id") in state["allowed_document_ids"]]
    complete = len(sources) <= retrieval_service.full_scan_max_chunks() if full_scan else None
    return ToolResult(
        tool=step.tool, status="success" if sources else "empty", sources=sources,
        coverage={"full_scan_required": full_scan, "full_scan_complete": complete},
    )
