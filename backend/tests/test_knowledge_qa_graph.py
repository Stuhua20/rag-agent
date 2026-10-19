import json
from threading import Event
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.agents.budget import RunBudget
from app.agents.contracts import ToolStep
from app.agents.knowledge_qa.evidence_coverage import assess_coverage
from app.agents.knowledge_qa.tools import execute_tool
from app.core.config import Settings, settings
from app.routers import chat as chat_routes
from app.services.chat_service import ChatService
from app.services.answer_quality_service import answer_quality_service
from app.services.json_store_service import json_store
from app.services.llm_service import llm_service
from app.services.query_understanding_service import query_understanding_service
from app.services.retrieval_service import retrieval_service


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "chat_runtime", "langgraph")
    monkeypatch.setattr(json_store, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "storage_dir", tmp_path / "storage")
    json_store.initialize()
    config = json_store.read_json("settings.json")
    config["retrieval"].update(search_mode="keyword", score_threshold=0.05, max_chunks_per_doc=0)
    json_store.write_json("settings.json", config)
    for doc_id, company, amount in (("a", "甲公司", 100), ("b", "乙公司", 900)):
        json_store.add_item("documents.json", {"id": doc_id, "status": "indexed", "file_name": f"{doc_id}.csv"})
        json_store.add_item("sheets.json", {"id": "sheet-" + doc_id, "document_id": doc_id,
                            "sheet_name": "销售", "headers": ["客户", "销售额", "付款条件"]})
        json_store.add_item("chunks.json", {
            "id": "chunk-" + doc_id, "document_id": doc_id, "sheet_id": "sheet-" + doc_id,
            "sheet_name": "销售", "row_start": 2, "row_end": 2,
            "content": f"行 2：客户={company}；销售额={amount}；付款条件=交货后30天付款",
            "metadata": {"file_name": f"{doc_id}.csv", "sheet_name": "销售"},
        })
        json_store.add_item("embeddings.json", {"chunk_id": "chunk-" + doc_id, "document_id": doc_id, "vector": []})
    result = ChatService()
    yield result
    result.close()


def fixed_plan(question, intent="lookup", queries=None):
    return {"resolved_question": question, "intent": intent, "sub_queries": [question],
            "retrieval_queries": queries or [question], "retrieval": {"need_full_scan": False}, "filters": {}}


def done(events):
    assert events[-1]["event"] == "done", events
    return events[-1]["data"]


def test_default_configuration_uses_langgraph(monkeypatch):
    monkeypatch.delenv("CHAT_RUNTIME", raising=False)
    assert Settings().chat_runtime == "langgraph"


def test_lookup_graph_persists_final_result_and_checkpoint(service):
    question = "甲公司销售额是多少？"
    with patch.object(query_understanding_service, "plan", return_value=fixed_plan(question)):
        events = list(service.ask_stream(question))
    result = done(events)
    assert result["status"] == "answered"
    assert result["quality"]["agent"]["retrieval_rounds"] == 1
    messages = service.list_messages(result["conversation_id"])
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[-1]["content"] == result["answer"]
    state = service.agent_runtime().graph.get_state({"configurable": {"thread_id": result["run_id"]}})
    assert state.values["quality"] == result["quality"]
    assert "service" not in state.values


def test_retired_table_conversation_continues_qa_without_touching_old_data(service):
    conversation = service.create_conversation()
    json_store.update_item('conversations.json', conversation['id'], {
        'agent_mode': 'table_analysis', 'table_target': {'document_id': 'a', 'sheet_id': 'sheet-a'},
    })
    archived = json_store.data_dir / 'table_analysis' / 'tables.sqlite'
    archived.parent.mkdir(parents=True)
    archived.write_bytes(b'archived table data must not be opened or modified')
    attachment = json_store.data_dir / 'attachments' / conversation['id'] / 'old.csv'
    attachment.parent.mkdir(parents=True)
    attachment.write_text('编号,金额\n001,10\n')
    old_message = json_store.add_item('messages.json', {
        'id': 'historic-table-answer', 'conversation_id': conversation['id'], 'role': 'assistant',
        'content': '历史表格统计文本', 'analysis': {'dataset': {'dataset_id': 'old-version'}}, 'sources': [],
    })
    question = '甲公司付款条件是什么？'
    with patch.object(query_understanding_service, 'plan', return_value=fixed_plan(question)):
        result = service.ask(question, conversation['id'])
    assert result['status'] == 'answered'
    assert result['quality']['agent']['workflow_version'] == 'knowledge-qa-v2'
    assert result['quality']['evidence_review']['mode'] == 'mock'
    assert result['quality']['evidence_review']['passed'] is None
    assert service.list_messages(conversation['id'])[0] == old_message
    assert archived.read_bytes() == b'archived table data must not be opened or modified'
    assert attachment.read_text() == '编号,金额\n001,10\n'


def test_retired_requests_are_rejected_and_routes_are_unregistered(service):
    from pydantic import ValidationError
    from app.schemas.chat import ChatRequest
    from app.schemas.conversation import CreateConversationRequest, UpdateConversationRequest
    from app.main import app
    from app.routers.prompts import list_prompts
    for extra in ({'attachment_ids': ['old']}, {'data_blocks': []}, {'clarification_response': {}}, {'timezone': 'Asia/Shanghai'}):
        with pytest.raises(ValidationError):
            ChatRequest(question='付款条件是什么？', **extra)
    with pytest.raises(ValidationError):
        ToolStep(tool='analyze_table')
    with pytest.raises(ValidationError):
        CreateConversationRequest(agent_mode='table_analysis')
    with pytest.raises(ValidationError):
        UpdateConversationRequest(expected_scope_revision=0, document_scope={'mode':'all'}, table_target=None)
    paths = app.openapi()['paths']
    assert not any(path.startswith('/api/analysis') or '/attachments' in path for path in paths)
    assert all(p['path'].split('/')[0] not in {'table_analysis', 'unified_chat'} for p in list_prompts())


def test_targeted_retrieval_fills_missing_company(service):
    question = "比较甲公司和乙公司的付款条件"
    sources = retrieval_service.sources_for_chunk_ids(["chunk-a", "chunk-b"])
    with patch.object(query_understanding_service, "plan", return_value=fixed_plan(question, "comparison")), patch.object(
        retrieval_service, "search_multiple", side_effect=[[sources[0]], [sources[1]]],
    ) as search:
        result = done(list(service.ask_stream(question)))
    assert result["status"] == "answered"
    assert result["quality"]["agent"]["retrieval_rounds"] == 2
    assert "乙公司" in " ".join(search.call_args.args[0])
    assert all(item["status"] == "covered" for item in result["quality"]["agent"]["coverage"])


def test_empty_results_are_bounded_and_never_call_answer_model(service):
    question = "比较甲公司和乙公司的付款条件"
    with patch.object(query_understanding_service, "plan", return_value=fixed_plan(question, "comparison")), patch.object(
        retrieval_service, "search_multiple", return_value=[],
    ) as search, patch.object(llm_service, "generate_answer_stream") as model:
        result = done(list(service.ask_stream(question)))
    assert result["status"] == "insufficient_evidence"
    assert search.call_count <= 3
    assert "乙公司" in result["answer"]
    model.assert_not_called()


def test_company_name_alone_does_not_cover_payment(service):
    question = "比较甲公司和乙公司的付款条件"
    sources = retrieval_service.sources_for_chunk_ids(["chunk-a", "chunk-b"])
    sources[1]["content"] = "乙公司主营办公用品。"
    with patch.object(query_understanding_service, "plan", return_value=fixed_plan(question, "comparison")), patch.object(
        retrieval_service, "search_multiple", return_value=sources,
    ), patch("app.agents.knowledge_qa.nodes.execute_tool", wraps=execute_tool):
        # Remove the underlying payment clause too, so a legitimate context read cannot fill it.
        chunks = json_store.list_items("chunks.json")
        chunks[1]["content"] = sources[1]["content"]
        json_store.write_json("chunks.json", chunks)
        result = done(list(service.ask_stream(question)))
    assert result["status"] == "insufficient_evidence"


def test_selected_scope_controls_metadata_search_and_final_sources(service):
    conversation = service.create_conversation(document_scope={"mode": "selected", "document_ids": ["a"]})
    result = service.ask("甲公司销售额是多少？", conversation["id"])
    assert result["status"] == "answered"
    assert "100" in result["answer"] and "1000" not in result["answer"]
    assert {item["document_id"] for item in result["sources"]} == {"a"}
    assert result["quality"]["answer_verifier"]["passed"]


def test_clarification_skips_tools(service):
    with patch.object(query_understanding_service, "plan", return_value={
        "needs_clarification": True, "clarification_question": "你指的是哪家公司？",
    }), patch.object(retrieval_service, "search_multiple") as search:
        result = done(list(service.ask_stream("它呢？")))
    assert result["status"] == "clarification_required"
    search.assert_not_called()


def test_scope_is_frozen_when_other_window_changes_it(service):
    conversation = service.create_conversation(document_scope={"mode": "selected", "document_ids": ["a"]})
    stream = service.ask_stream("甲公司销售额是多少？", conversation["id"])
    assert next(stream)["event"] == "run_started"
    service.update_document_scope(conversation["id"], {"mode": "selected", "document_ids": ["b"]}, 0)
    result = done(list(stream))
    assert {item["document_id"] for item in result["sources"]} == {"a"}
    assert service.list_messages(conversation["id"])[-1]["scope_revision"] == 0


def test_busy_reservation_releases_even_if_never_started(service):
    conversation = service.create_conversation()
    stream = service.ask_stream("问题", conversation["id"])
    with pytest.raises(HTTPException) as error:
        service.ask_stream("另一个问题", conversation["id"])
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "conversation_busy"
    stream.close()
    replacement = service.ask_stream("问题", conversation["id"])
    replacement.close()


def test_model_exception_emits_error_without_success(service):
    question = "甲公司销售额是多少？"
    with patch.object(query_understanding_service, "plan", return_value=fixed_plan(question)), patch.object(
        llm_service, "generate_answer_stream", side_effect=RuntimeError("offline"),
    ):
        events = list(service.ask_stream(question))
    assert events[-1]["event"] == "error"
    assert not any(event["event"] == "done" for event in events)
    assert [item["role"] for item in json_store.list_items("messages.json")] == ["user"]


def test_stream_is_incremental_and_verification_replaces_draft(service):
    question = "甲公司销售额是多少？"
    generated = []
    consumed = Event()

    def model(*args, **kwargs):
        generated.append("first")
        yield "甲公司销售额为999元。"
        assert consumed.wait(5), "custom token was buffered until the node finished"
        generated.append("finished")

    with patch.object(query_understanding_service, "plan", return_value=fixed_plan(question)), patch.object(
        llm_service, "generate_answer_stream", side_effect=model,
    ), patch.object(answer_quality_service, "verify_answer", wraps=answer_quality_service.verify_answer) as verifier:
        stream = service.ask_stream(question)
        for event in stream:
            if event["event"] == "delta":
                assert generated == ["first"]
                verifier.assert_not_called()
                consumed.set()
                break
        result = done(list(stream))
    assert result["status"] == "verification_failed"
    assert "999" not in result["answer"]
    assert service.list_messages(result["conversation_id"])[-1]["content"] == result["answer"]


def test_llm_budget_stops_nested_calls_without_success_claim(service, monkeypatch):
    monkeypatch.setattr(settings, "agent_max_llm_calls", 1)
    result = done(list(service.ask_stream("甲公司销售额是多少？")))
    assert result["status"] == "insufficient_evidence"
    assert result["quality"]["agent"]["llm_calls"] == 1
    assert result["quality"]["agent"]["stop_reason"] == "llm_budget"


def test_tool_budget_stops_before_extra_calls(service, monkeypatch):
    monkeypatch.setattr(settings, "agent_max_tool_calls", 1)
    question = "比较甲公司和乙公司的付款条件"
    sources = retrieval_service.sources_for_chunk_ids(["chunk-a"])
    with patch.object(query_understanding_service, "plan", return_value=fixed_plan(question, "comparison")), patch.object(
        retrieval_service, "search_multiple", return_value=sources,
    ) as search:
        result = done(list(service.ask_stream(question)))
    assert search.call_count == 1
    assert result["status"] == "insufficient_evidence"
    assert result["quality"]["agent"]["tool_calls"] == 1


def test_full_scan_truncation_never_becomes_complete_by_replanning(service, monkeypatch):
    monkeypatch.setattr(retrieval_service, "full_scan_max_chunks", lambda: 1)
    question = "比较甲公司和乙公司的付款条件"
    with patch.object(query_understanding_service, "plan", return_value=fixed_plan(question, "comparison")):
        result = service.ask(question)
    assert result["status"] == "insufficient_evidence"
    assert result["quality"]["agent"]["retrieval_rounds"] == 1
    assert not result["quality"]["evidence_gate"]["full_scan_complete"]


def test_deleted_session_cannot_be_resurrected_by_active_run(service):
    conversation = service.create_conversation()
    stream = service.ask_stream("甲公司销售额是多少？", conversation["id"])
    next(stream)
    service.delete_conversation(conversation["id"])
    events = list(stream)
    assert not any(event["event"] == "done" for event in events)
    assert service.list_messages(conversation["id"]) == []
    assert service.agent_runtime().store.conn.execute("SELECT count(*) FROM agent_runs").fetchone()[0] == 0


def test_atomic_run_message_is_unique(service):
    conversation = service.create_conversation()
    for _ in range(2):
        service._add_message(conversation["id"], "assistant", "完成", [], run_id="same-run")
    assert len(service.list_messages(conversation["id"])) == 1


def test_http_preserves_fields_and_preflight_scope_conflict(service, monkeypatch):
    monkeypatch.setattr(chat_routes, "chat_service", service)
    app = FastAPI()
    app.include_router(chat_routes.router)
    conversation = service.create_conversation()
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"question": "甲公司销售额是多少？", "conversation_id": conversation["id"]})
        assert response.status_code == 200
        assert response.json()["run_id"]
        response = client.post("/api/chat/stream", json={"question": "问题", "conversation_id": conversation["id"], "expected_scope_revision": 9})
        assert response.status_code == 409
        assert not response.headers.get("content-type", "").startswith("text/event-stream")


def test_model_coverage_rejects_invented_quote_and_id(service):
    requirements = [
        {"id": "req-1", "query": "甲公司付款条件", "target": "甲公司", "terms": ["付款"]},
        {"id": "req-2", "query": "乙公司付款条件", "target": "乙公司", "terms": ["付款"]},
    ]
    with patch.object(llm_service, "_get_config", return_value={"mock": False}), patch.object(
        llm_service, "generate_answer", return_value=json.dumps({"items": [{
            "requirement_id": "req-1", "status": "covered", "evidence_ids": ["invented"], "quote": "甲公司可以永久免付费用",
        }]}),
    ):
        result = assess_coverage(requirements, retrieval_service.sources_for_chunk_ids(["chunk-a"]), lambda _: "{requirements}{evidence}")
    assert result[0]["status"] == "uncertain"


def test_invalid_tool_is_rejected():
    with pytest.raises(ValueError):
        ToolStep(tool="execute_python")


def test_budget_deadline_and_cancel_are_enforced():
    from app.agents.budget import BudgetExceeded, RunCancelled
    budget = RunBudget(seconds=-1)
    with pytest.raises(BudgetExceeded):
        budget.check()
    budget.cancelled.set()
    with pytest.raises(RunCancelled):
        budget.check()


def test_requirements_preserve_subtasks_and_dates():
    from app.agents.knowledge_qa.evidence_coverage import requirements_for
    requirements = requirements_for("2024年甲乙两家公司情况", {"sub_queries": [
        "2024年甲公司销售额", "2024年乙公司付款条件",
    ]})
    assert len(requirements) == 2
    assert requirements[0]["target"] == "甲公司"
    assert "销售额" in requirements[0]["terms"]
    assert "付款" in requirements[1]["terms"]
    assert all("2024年" in item["query"] for item in requirements)


def test_multi_lookup_cannot_cover_both_companies_with_one_source(service):
    question = "分别列出甲公司和乙公司的付款条件"
    source = retrieval_service.sources_for_chunk_ids(["chunk-a"])
    with patch.object(query_understanding_service, "plan", return_value=fixed_plan(question)), patch.object(
        retrieval_service, "search_multiple", return_value=source,
    ):
        result = service.ask(question)
    assert result["status"] == "insufficient_evidence"
    assert any(item["status"] == "missing" for item in result["quality"]["agent"]["coverage"])


def test_sync_completion_does_not_become_cancelled(service):
    result = service.ask("甲公司销售额是多少？")
    record = service.agent_runtime().store.conn.execute(
        "SELECT status FROM agent_runs WHERE run_id=?", (result["run_id"],),
    ).fetchone()
    assert record[0] == "answered"


def test_document_deletion_emits_explicit_failure(service):
    conversation = service.create_conversation(document_scope={"mode": "selected", "document_ids": ["a"]})
    stream = service.ask_stream("甲公司销售额是多少？", conversation["id"])
    next(stream)
    json_store.delete_item("documents.json", "a")
    events = list(stream)
    assert events[-1]["event"] == "error"
    assert events[-1]["data"]["code"] == "document_changed"
    assert [item["role"] for item in service.list_messages(conversation["id"])] == ["user"]


def test_forged_document_filter_is_ignored(service):
    conversation = service.create_conversation(document_scope={"mode": "selected", "document_ids": ["a"]})
    result = service.ask("甲公司销售额是多少？", conversation["id"], filters={"document_ids": ["b"]})
    assert "100" in result["answer"] and "900" not in result["answer"]
    assert {item["document_id"] for item in result["sources"]} == {"a"}


def test_too_many_goals_asks_to_narrow_instead_of_dropping_tasks(service):
    question = "查询这些公司的付款条件"
    plan = fixed_plan(question)
    plan["sub_queries"] = [f"{name}公司付款条件" for name in "甲乙丙丁戊己庚"]
    with patch.object(query_understanding_service, "plan", return_value=plan):
        result = service.ask(question)
    assert result["status"] == "clarification_required"
    assert result["quality"]["agent"]["tool_calls"] == 0


def test_closing_incremental_stream_cancels_without_final_message(service):
    from app.agents.budget import current_budget
    question = "甲公司销售额是多少？"

    def model(*args, **kwargs):
        yield "甲公司"
        assert current_budget.get().cancelled.wait(5)
        yield "销售额"

    with patch.object(query_understanding_service, "plan", return_value=fixed_plan(question)), patch.object(
        llm_service, "generate_answer_stream", side_effect=model,
    ):
        stream = service.ask_stream(question)
        for event in stream:
            if event["event"] == "delta":
                break
        stream.close()
    assert [item["role"] for item in json_store.list_items("messages.json")] == ["user"]
    assert not service.agent_runtime().active


def test_saved_result_with_failed_ledger_update_requires_reconciliation(service):
    runtime = service.agent_runtime()
    record = runtime.store.record

    def fail_terminal(run_id, conversation_id, status, summary):
        if status == "answered":
            raise RuntimeError("simulated ledger failure")
        record(run_id, conversation_id, status, summary)

    with patch.object(runtime.store, "record", side_effect=fail_terminal):
        events = list(service.ask_stream("甲公司销售额是多少？"))
    assert events[-1]["event"] == "error"
    assert events[-1]["data"]["code"] == "needs_reconciliation"
    assert len([item for item in json_store.list_items("messages.json") if item["role"] == "assistant"]) == 1


def test_unresolved_conflicts_are_disclosed_in_final_answer(service):
    question = "比较甲公司和乙公司的付款条件"
    with patch.object(query_understanding_service, "plan", return_value=fixed_plan(question, "comparison")), patch(
        "app.agents.knowledge_qa.nodes.assess_coverage", return_value=[
            {"requirement_id": "req-1", "status": "conflict", "evidence_ids": ["chunk-a"], "quote": ""},
            {"requirement_id": "req-2", "status": "covered", "evidence_ids": ["chunk-b"], "quote": ""},
        ],
    ):
        result = service.ask(question)
    assert result["status"] == "insufficient_evidence"
    assert "冲突" in result["answer"]


CASES = json.loads((Path(__file__).parent / "fixtures" / "knowledge_qa_cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[item["id"] for item in CASES])
def test_acceptance_cases(service, case, monkeypatch):
    """Synthetic corpus checks flow/grounding contracts, not real-model answer quality."""
    conversation = service.create_conversation(document_scope={"mode": "selected", "document_ids": case.get("scope", ["a", "b"])})
    if case.get("history"):
        service._add_message(conversation["id"], "user", case["history"], [], scope_context=conversation)
    resolved = case.get("resolved", case["question"])
    plan = fixed_plan(resolved, case.get("intent", "lookup"))
    plan["sub_queries"] = case.get("sub_queries", [resolved])
    if case.get("clarify"):
        plan.update(needs_clarification=True, clarification_question="请明确要查询的公司。")
    monkeypatch.setattr(query_understanding_service, "plan", lambda *args: plan)
    monkeypatch.setattr(llm_service, "_mock_answer_stream", lambda prompt: iter([llm_service._mock_answer(prompt)]))
    result = service.ask(case["question"], conversation["id"])
    assert result["status"] == case["status"]
    if case.get("contains"):
        assert case["contains"] in result["answer"]
    assert set(case["evidence"]).issubset({source["chunk_id"] for source in result["sources"]})
    assert {source["document_id"] for source in result["sources"]}.issubset(set(case.get("scope", ["a", "b"])))
    assert result["quality"]["agent"]["retrieval_rounds"] <= 3


@pytest.fixture
def real_review(service, monkeypatch):
    """Exercise actual model wrappers/budget and actual reviewer validation without network."""
    config = json_store.read_json("settings.json")
    config["llm"]["mock"] = False
    json_store.write_json("settings.json", config)
    monkeypatch.setattr(settings, "evidence_review_enabled", True)
    monkeypatch.setattr(settings, "evidence_review_max_revisions", 1)
    question = "甲公司销售额是多少？"
    monkeypatch.setattr(query_understanding_service, "plan", lambda *args: fixed_plan(question))
    control = {"draft": "甲公司销售额为100。", "repair": "甲公司销售额为100。",
               "statuses": ["supported"], "reviews": [], "repairs": [], "raw": None, "error": None}
    monkeypatch.setattr(llm_service, "_api_answer_stream", lambda *args: iter([control["draft"]]))

    def api(prompt, *args):
        if "【审查输入】\n" not in prompt:
            control["repairs"].append(json.loads(prompt.split("【修订输入：原始问题、当前草稿、证据、问题】\n", 1)[1]))
            return control["repair"]
        payload = json.loads(prompt.split("【审查输入】\n", 1)[1])
        control["reviews"].append(payload)
        if control["error"]:
            raise control["error"]
        if control["raw"] is not None:
            return control["raw"]
        statuses = control["statuses"]
        status = statuses[min(len(control["reviews"]) - 1, len(statuses) - 1)]
        return json.dumps({
            "units": [{"unit_id": unit["id"], "status": status,
                       "evidence_refs": [{"evidence_id": payload["evidence"][0]["id"], "quote": payload["evidence"][0]["text"]}],
                       "issues": [] if status == "supported" else ["条件与证据不符，请按原文修订"]}
                      for unit in payload["answer_units"]],
            "tasks": [{"requirement_id": task["id"], "status": "answered", "reason": "已回应任务",
                       "answer_unit_ids": [unit["id"] for unit in payload["answer_units"]]}
                      for task in payload["requirements"]],
        }, ensure_ascii=False)
    monkeypatch.setattr(llm_service, "_api_answer", api)
    return control


def test_reviewed_answer_publishes_only_after_review_and_persistence(service, real_review):
    stream = service.ask_stream("甲公司销售额是多少？")
    for event in stream:
        if event["event"] in {"sources", "delta"}:
            assert len(real_review["reviews"]) == 1
            assert json_store.list_items("messages.json")[-1]["role"] == "assistant"
        if event["event"] == "done":
            result = event["data"]
    assert result["status"] == "answered"
    assert result["quality"]["evidence_review"]["passed"] is True
    assert result["quality"]["agent"]["llm_calls"] == 2
    assert not real_review["repairs"]


def test_semantic_failure_repairs_once_and_rechecks(service, real_review):
    real_review.update(statuses=["contradicted", "supported"], draft="甲公司无需审批。")
    result = service.ask("甲公司销售额是多少？")
    assert result["status"] == "answered"
    assert result["answer"] == real_review["repair"]
    assert len(real_review["reviews"]) == 2 and len(real_review["repairs"]) == 1
    assert real_review["repairs"][0]["draft"] == real_review["draft"]
    report = result["quality"]["evidence_review"]
    assert report["revision_round"] == 1 and len(report["history"]) == 2
    assert len(report["rule_history"]) == 2
    assert result["quality"]["agent"]["llm_calls"] == 4
    steps = result["quality"]["agent"]["steps"]
    reviews = [step for step in steps if step["event"] == "step_started" and step["step_id"].startswith("evidence_review:")]
    assert len({step["step_id"] for step in reviews}) == 2
    assert reviews[-1]["label"] == "复核回答"


def test_rule_failure_preserves_original_draft_for_repair(service, real_review):
    real_review["draft"] = "甲公司销售额999。"
    result = service.ask("甲公司销售额是多少？")
    assert result["status"] == "answered"
    assert real_review["repairs"][0]["draft"] == "甲公司销售额999。"
    assert len(real_review["reviews"]) == 1
    assert result["quality"]["agent"]["llm_calls"] == 3


def test_second_semantic_failure_never_leaks_draft_or_loops(service, real_review):
    real_review.update(statuses=["contradicted"], draft="甲公司无需审批。", repair="甲公司一定可以申请。")
    events = list(service.ask_stream("甲公司销售额是多少？"))
    result = done(events)
    assert result["status"] == "verification_failed"
    assert len(real_review["repairs"]) == 1 and len(real_review["reviews"]) == 2
    assert result["quality"]["evidence_gate"]["passed"] is True
    assert [item["data"]["text"] for item in events if item["event"] == "delta"] == [result["answer"]]
    assert "无需审批" not in result["answer"] and "一定可以" not in result["answer"]
    assert service.list_messages(result["conversation_id"])[-1]["content"] == result["answer"]


@pytest.mark.parametrize("failure", ["not-json", '{"units":[],"tasks":[]}', RuntimeError("offline")])
def test_unavailable_reviewer_never_repairs_or_approves(service, real_review, failure):
    if isinstance(failure, Exception): real_review["error"] = failure
    else: real_review["raw"] = failure
    result = service.ask("甲公司销售额是多少？")
    assert result["status"] == "review_unavailable"
    assert result["quality"]["evidence_review"]["passed"] is None
    assert result["quality"]["evidence_gate"]["passed"] is True
    assert not real_review["repairs"]
    assert real_review["draft"] not in result["answer"]


def test_zero_revision_setting_stops_after_first_failure(service, real_review, monkeypatch):
    monkeypatch.setattr(settings, "evidence_review_max_revisions", 0)
    real_review["statuses"] = ["unsupported"]
    result = service.ask("甲公司销售额是多少？")
    assert result["status"] == "verification_failed"
    assert len(real_review["reviews"]) == 1 and not real_review["repairs"]


def test_review_budget_failure_does_not_publish_unreviewed_answer(service, real_review, monkeypatch):
    monkeypatch.setattr(settings, "agent_max_llm_calls", 1)
    result = service.ask("甲公司销售额是多少？")
    assert result["status"] == "budget_exceeded"
    assert result["quality"]["evidence_review"]["passed"] is None
    assert result["quality"]["agent"]["llm_calls"] == 0
    assert not real_review["reviews"]


def test_repair_requires_budget_for_both_repair_and_recheck(service, real_review, monkeypatch):
    monkeypatch.setattr(settings, "agent_max_llm_calls", 3)
    real_review["statuses"] = ["unsupported"]
    result = service.ask("甲公司销售额是多少？")
    assert result["status"] == "budget_exceeded"
    assert result["quality"]["agent"]["llm_calls"] == 2
    assert not real_review["repairs"]


def test_disabled_review_keeps_original_stream_and_marks_skipped(service, real_review, monkeypatch):
    monkeypatch.setattr(settings, "evidence_review_enabled", False)
    result = service.ask("甲公司销售额是多少？")
    assert result["status"] == "answered" and not real_review["reviews"]
    assert result["quality"]["evidence_review"]["mode"] == "disabled"
    assert result["quality"]["evidence_review"]["passed"] is None
    assert result["quality"]["agent"]["workflow_version"] == "knowledge-qa-v1"


def test_document_deleted_during_review_prevents_final_answer(service, real_review, monkeypatch):
    original = llm_service._api_answer
    def deleting_reviewer(*args):
        response = original(*args)
        json_store.delete_item("documents.json", "a")
        return response
    monkeypatch.setattr(llm_service, "_api_answer", deleting_reviewer)
    events = list(service.ask_stream("甲公司销售额是多少？"))
    assert events[-1]["event"] == "error"
    assert events[-1]["data"]["code"] == "document_changed"
    assert not any(item["event"] in {"delta", "done"} for item in events)


def test_question_number_cannot_authorize_a_business_fact(service, real_review):
    real_review["draft"] = "甲公司销售额999。"
    question = "甲公司的销售额是999吗？"
    report = answer_quality_service.verify_answer(real_review["draft"], question,
        retrieval_service.sources_for_chunk_ids(["chunk-a"]), preserve_draft=True)
    assert not report["passed"]
    assert report["answer"] == real_review["draft"]


def test_review_deadline_never_publishes_draft(service, real_review, monkeypatch):
    from app.agents.budget import BudgetExceeded
    real_review["error"] = BudgetExceeded("time_budget")
    events = list(service.ask_stream("甲公司销售额是多少？"))
    result = done(events)
    assert result["status"] == "budget_exceeded"
    assert result["quality"]["agent"]["stop_reason"] == "time_budget"
    assert real_review["draft"] not in result["answer"]
    assert result["quality"]["evidence_review"]["passed"] is None


def test_cancel_during_review_cannot_save_or_publish_answer(service, real_review):
    from app.agents.budget import RunCancelled
    real_review["error"] = RunCancelled("cancelled")
    events = list(service.ask_stream("甲公司销售额是多少？"))
    assert events[-1]["event"] == "error"
    assert not any(item["event"] in {"delta", "done"} for item in events)
    assert [item["role"] for item in json_store.list_items("messages.json")] == ["user"]
    assert not service.agent_runtime().active


def test_failed_repair_does_not_publish_original_draft(service, real_review, monkeypatch):
    original = llm_service._api_answer
    real_review["statuses"] = ["unsupported"]
    def failing_repair(prompt, *args):
        if "【审查输入】" not in prompt:
            raise RuntimeError("repair offline")
        return original(prompt, *args)
    monkeypatch.setattr(llm_service, "_api_answer", failing_repair)
    result = service.ask("甲公司销售额是多少？")
    assert result["status"] == "review_unavailable"
    assert result["quality"]["agent"]["stop_reason"] == "repair_unavailable"
    assert real_review["draft"] not in result["answer"]


def test_no_revision_rule_failure_does_not_claim_semantic_review(service, real_review, monkeypatch):
    real_review["draft"] = "甲公司销售额999。"
    monkeypatch.setattr(settings, "evidence_review_max_revisions", 0)
    result = service.ask("甲公司销售额是多少？")
    assert result["status"] == "verification_failed"
    assert not real_review["reviews"] and not real_review["repairs"]
    assert result["quality"]["evidence_review"]["passed"] is None
    assert result["quality"]["evidence_review"]["reason"] == "rule_failed"


def test_selected_scope_is_preserved_in_review_and_repair(service, real_review):
    real_review["statuses"] = ["unsupported", "supported"]
    conversation = service.create_conversation(document_scope={"mode": "selected", "document_ids": ["a"]})
    result = service.ask("甲公司销售额是多少？", conversation["id"])
    assert result["status"] == "answered"
    assert all({item["id"] for item in payload["evidence"]} == {"chunk-a"} for payload in real_review["reviews"])
    assert {item["id"] for item in real_review["repairs"][0]["evidence"]} == {"chunk-a"}


def test_real_oversized_draft_is_not_silently_truncated_or_published(service, real_review):
    real_review["draft"] = "设备说明" * 3100
    result = service.ask("甲公司销售额是多少？")
    assert result["status"] == "review_unavailable"
    assert not real_review["reviews"]
    assert len(result["answer"]) < 300
