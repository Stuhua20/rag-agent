import json

from langgraph.runtime import Runtime

from app.agents.budget import BudgetExceeded
from app.agents.contracts import Replan, ToolStep
from app.agents.knowledge_qa.evidence_coverage import assess_coverage, requirements_for
from app.agents.knowledge_qa.state import KnowledgeQAState
from app.agents.knowledge_qa.tools import action_key, execute_tool
from app.agents.knowledge_qa.runtime import RunContext
from app.services.answer_quality_service import answer_quality_service
from app.services.conversation_context_service import conversation_context_service
from app.services.knowledge_metadata_service import knowledge_metadata_service
from app.services.llm_service import llm_service
from app.services.query_understanding_service import query_understanding_service


LABELS = {
    "understand": "理解问题", "execute": "检索资料", "assess": "检查证据覆盖",
    "replan": "规划补充检索", "generate": "生成回答", "verify": "校验回答",
    "clarify": "需要补充信息", "fallback": "整理依据缺口", "finalize": "保存最终结果",
}


def guarded(node):
    def invoke(state: KnowledgeQAState, runtime: Runtime[RunContext]) -> dict:
        context = runtime.context
        node_name = node.__name__
        step_id = f"{node_name}:{state.get('round', 0)}"
        context.emit("step_started", {"step_id": step_id, "label": LABELS[node_name]})
        try:
            context.check(check_budget=node_name in {"understand", "execute", "assess", "replan", "generate", "verify"})
            with context.budget.activate():
                update = node(state, runtime)
        except BudgetExceeded as exc:
            update = {"halted": True, "stop_reason": str(exc), "status": "insufficient_evidence"}
        context.emit("step_done", {"step_id": step_id, "label": LABELS[node_name]})
        return update
    return invoke


def understand(state: KnowledgeQAState, runtime: Runtime[RunContext]) -> dict:
    context = runtime.context
    history = conversation_context_service.build_context(
        context.history, scope_revision=state["scope_revision"],
    )[-8000:]
    metadata = knowledge_metadata_service.snapshot(state["original_question"], document_ids=state["allowed_document_ids"])
    plan = query_understanding_service.plan(state["original_question"], history, metadata, context.filters)
    resolved = plan.get("resolved_question") or state["original_question"]
    requirements = requirements_for(resolved, plan)
    if len(requirements) > 6:
        plan = {**plan, "needs_clarification": True,
                "clarification_question": "本次问题包含超过六项检索任务，请先选择要查询的对象或要点。"}
        requirements = []
    context.emit("plan", {"label": "检索任务已确定", "tasks": [item["query"] for item in requirements]})
    return {
        "conversation_context": history, "query_plan": {**plan, "document_scope": state["document_scope"]},
        "resolved_question": resolved, "requirements": requirements,
        "pending_steps": [ToolStep(
            tool="search_knowledge", queries=(plan.get("retrieval_queries") or [resolved])[:3],
        ).model_dump()],
    }


def clarify(state: KnowledgeQAState, runtime: Runtime[RunContext]) -> dict:
    return {"status": "clarification_required", "stop_reason": "ambiguous_question",
            "final_answer": state["query_plan"]["clarification_question"]}


def select_evidence(sources: list[dict], requirements: list[dict]) -> list[dict]:
    """Preserve task diversity before applying bounded checkpoint/prompt size."""
    ordered = []
    for requirement in requirements:
        for source in sources:
            text = str(source.get("content") or "").casefold()
            if requirement["target"] and requirement["target"].casefold() in text:
                ordered.append(source)
                break
    ordered.extend(sources)
    result, seen, chars = [], set(), 0
    for source in ordered:
        key = (source.get("document_id"), source.get("chunk_id"))
        if key in seen:
            continue
        content = str(source.get("content") or "")[:6000]
        if chars + len(content) > 24000 or len(result) >= 20:
            continue
        result.append({**source, "content": content})
        seen.add(key)
        chars += len(content)
    return result


def execute(state: KnowledgeQAState, runtime: Runtime[RunContext]) -> dict:
    context = runtime.context
    sources = list(state.get("sources", []))
    before = {item["chunk_id"] for item in sources}
    executed = list(state.get("executed_actions", []))
    retrieval_state = state.get("retrieval_state", {})
    for raw in state["pending_steps"]:
        step = ToolStep.model_validate(raw)
        key = action_key(step, state["allowed_document_ids"])
        if key in executed:
            continue
        result = execute_tool(step, state, context)
        executed.append(key)
        context.emit("tool_result", {"tool": step.tool, "status": result.status, "source_count": len(result.sources)})
        sources.extend(result.sources)
        if result.coverage:
            retrieval_state = result.coverage
    selected = select_evidence(sources, state["requirements"])
    after = {item["chunk_id"] for item in selected}
    # Losing any full-scan evidence cannot be reported as complete generation coverage.
    if retrieval_state.get("full_scan_required"):
        if len({item["chunk_id"] for item in sources}) > len(after):
            retrieval_state = {**retrieval_state, "full_scan_complete": False}
    return {"sources": selected, "executed_actions": executed, "retrieval_state": retrieval_state,
            "round": state.get("round", 0) + 1,
            "no_growth": state.get("no_growth", 0) + 1 if after == before else 0}


def assess(state: KnowledgeQAState, runtime: Runtime[RunContext]) -> dict:
    context = runtime.context
    report = answer_quality_service.evaluate_evidence(
        state["resolved_question"], state["query_plan"], state["sources"], state["retrieval_state"],
    )
    report.pop("fallback_answer", None)
    coverage = assess_coverage(
        state["requirements"], state["sources"], context.load_prompt,
    )
    missing = [item["requirement_id"] for item in coverage if item["status"] != "covered"]
    if missing:
        report = {**report, "passed": False, "reason": "部分检索任务尚无充分证据。",
                  "missing": [*report.get("missing", []), *missing]}
    return {"coverage": coverage, "evidence_report": report}


def replan(state: KnowledgeQAState, runtime: Runtime[RunContext]) -> dict:
    context = runtime.context
    missing = {item["requirement_id"] for item in state.get("coverage", []) if item["status"] != "covered"}
    requirements = [item for item in state["requirements"] if not missing or item["id"] in missing]
    candidates = [item["query"] for item in requirements]
    for item in requirements:
        candidates.extend(f"{item['query']} {term}" for term in item["terms"][1:])
    if not llm_service._get_config()["mock"]:
        prompt = context.load_prompt("agent/replan.md").replace(
            "{requirements}", json.dumps(requirements, ensure_ascii=False)
        ).replace("{executed_queries}", json.dumps(state["executed_actions"], ensure_ascii=False))
        try:
            raw = query_understanding_service._parse_json_object(llm_service.generate_answer(prompt))
            additions = Replan.model_validate(raw).queries
            candidates = [f"{item['query']} {query}" for item in requirements for query in additions] + candidates
        except BudgetExceeded:
            raise
        except Exception:
            pass  # bounded rule fallback
    # Filter individual queries as well as batches, so repackaging never repeats work.
    previous = set()
    for key in state["executed_actions"]:
        action, _ = json.loads(key)
        previous.update(query.casefold().strip() for query in action.get("queries", []))
    queries = list(dict.fromkeys(query.strip()[:2000] for query in candidates if query.strip()
                                and query.casefold().strip() not in previous))[:3]
    steps = []
    if queries:
        steps.append(ToolStep(tool="search_knowledge", queries=queries))
    if state["sources"]:
        step = ToolStep(tool="read_evidence_context", chunk_ids=[item["chunk_id"] for item in state["sources"][:3]])
        if action_key(step, state["allowed_document_ids"]) not in state["executed_actions"]:
            steps.append(step)
    return {"pending_steps": [item.model_dump() for item in steps],
            "stop_reason": "" if steps else "no_new_actions"}


def generate(state: KnowledgeQAState, runtime: Runtime[RunContext]) -> dict:
    context = runtime.context
    context.emit("sources", {"conversation_id": state["conversation_id"], "sources": state["sources"]})
    prompt = context.service._build_prompt(
        state["original_question"], state["sources"], state["query_plan"], state["conversation_context"],
        evidence_report=state["evidence_report"],
    )
    chunks = []
    for text in llm_service.generate_answer_stream(prompt, system_prompt=context.load_prompt("system/base.md")):
        context.budget.check()
        if text:
            chunks.append(text)
            context.emit("delta", {"text": text})
    answer = "".join(chunks)
    return {"final_answer": answer}


def verify(state: KnowledgeQAState, runtime: Runtime[RunContext]) -> dict:
    verification = answer_quality_service.verify_answer(
        state["final_answer"], state["resolved_question"], state["sources"],
        original_question=state["original_question"],
    )
    answer = verification.pop("answer")
    return {"final_answer": answer, "verifier_report": verification,
            "status": "answered" if verification["passed"] else "verification_failed",
            "stop_reason": "completed" if verification["passed"] else "verification_failed"}


def fallback(state: KnowledgeQAState, runtime: Runtime[RunContext]) -> dict:
    missing = {item["requirement_id"] for item in state.get("coverage", []) if item["status"] != "covered"}
    gaps = [item["query"] for item in state.get("requirements", []) if item["id"] in missing]
    answer = runtime.context.service._no_source_answer(runtime.context.conversation)
    if state.get("sources"):
        answer = "当前检索资料不足以支持完整回答。"
    conflict = any(item["status"] == "conflict" for item in state.get("coverage", []))
    if conflict:
        answer = "当前资料存在相互冲突的描述，无法确定可靠结论。请核对资料版本或适用条件。"
    if gaps and (state.get("sources") or len(state.get("requirements", [])) > 1):
        answer += ("\n\n仍未解决的要点：" if conflict else "\n\n尚缺少依据：") + "；".join(query.rstrip("。？?") for query in gaps) + "。"
    if state.get("halted"):
        answer = "本轮处理已达到执行预算，未能完成可靠回答。请缩小问题范围后重试。"
    if state.get("retrieval_state", {}).get("full_scan_required") and not state.get("retrieval_state", {}).get("full_scan_complete"):
        answer += "\n当前资料未覆盖完整计算或比较范围，请缩小范围后重试。"
    return {"status": "insufficient_evidence", "final_answer": answer,
            "stop_reason": state.get("stop_reason") or "retrieval_limit"}


def complete(state: KnowledgeQAState, runtime: Runtime[RunContext]) -> dict:
    context = runtime.context
    report = state.get("evidence_report", {"passed": False, "skipped": True})
    if state["status"] != "answered":
        report = {**report, "passed": False}
    quality = {
        "query_understanding": context.service._question_trace(state["original_question"], state.get("query_plan", {})),
        "evidence_gate": report,
        "answer_verifier": state.get("verifier_report", {"passed": None, "skipped": True}),
        "agent": {"workflow_version": state["workflow_version"], "run_id": state["run_id"],
                  "status": state["status"], "retrieval_rounds": state.get("round", 0),
                  "coverage": state.get("coverage", []), "stop_reason": state["stop_reason"],
                  "llm_calls": context.budget.llm_calls, "tool_calls": context.budget.tool_calls,
                  "steps": list(context.steps)},
    }
    context.check(check_budget=False)
    return {"quality": quality, "final_answer": state['final_answer'], "sources": state.get('sources', []),
            "status": state['status'], 'query_plan': state.get('query_plan', {})}


def finalize(state: KnowledgeQAState, runtime: Runtime[RunContext]) -> dict:
    result = complete(state, runtime)
    context = runtime.context
    context.service._add_message(
        state["conversation_id"], "assistant", state["final_answer"], state.get("sources", []), result['quality'],
        scope_context=context.conversation, run_id=state["run_id"], status=state["status"],
    )
    context.service._touch_conversation(state["conversation_id"])
    return result
