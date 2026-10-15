"""Isolated checks for Evidence Gate, Answer Verifier, and chat integration."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.answer_quality_service import answer_quality_service
from app.services.chat_service import ChatService
from app.services.json_store_service import json_store
from app.services.knowledge_metadata_service import knowledge_metadata_service
from app.services.llm_service import llm_service
from app.services.query_understanding_service import query_understanding_service
from app.schemas.chat import ChatResponse


def make_source(content: str, *, chunk_id: str = "chunk_test_1", score: float = 0.9) -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": "doc_sales",
        "sheet_id": "sheet_sales",
        "file_name": "sales.csv",
        "sheet_name": "sales",
        "row_start": 2,
        "row_end": 3,
        "score": score,
        "score_type": "similarity",
        "content": content,
    }


def check_evidence_gate() -> None:
    source = make_source("行 2：客户=甲公司；销售额=120000\n行 3：客户=乙公司；销售额=76000")

    comparison = answer_quality_service.evaluate_evidence(
        "甲公司和乙公司销售额对比",
        {"intent": "comparison"},
        [source],
        {"full_scan_required": True, "full_scan_complete": True, "deterministic": False},
    )
    assert comparison["passed"]
    assert comparison["evidence_units"] == 2

    incomplete = answer_quality_service.evaluate_evidence(
        "销售额排名",
        {"intent": "ranking"},
        [source],
        {"full_scan_required": True, "full_scan_complete": False, "deterministic": False},
    )
    assert not incomplete["passed"]
    assert "完整计算范围" in incomplete["reason"]

    one_record = answer_quality_service.evaluate_evidence(
        "月度销售额趋势",
        {"intent": "trend"},
        [make_source("行 2：月份=2025-01；销售额=120000")],
        {"full_scan_required": True, "full_scan_complete": True, "deterministic": False},
    )
    assert not one_record["passed"]

    deterministic = answer_quality_service.evaluate_evidence(
        "销售额排名",
        {"intent": "ranking"},
        [make_source("行 2：客户=甲公司；销售额=120000", score=1.0)],
        {"full_scan_required": True, "full_scan_complete": True, "deterministic": True},
    )
    assert deterministic["passed"]

    no_source = answer_quality_service.evaluate_evidence(
        "库存是多少",
        {"intent": "lookup"},
        [],
        {"full_scan_required": False, "full_scan_complete": None, "deterministic": False},
    )
    assert not no_source["passed"]

    weak_match = answer_quality_service.evaluate_evidence(
        "甲公司销售额是多少",
        {"intent": "lookup"},
        [make_source("行 2：客户=甲公司；销售额=120000", score=0.01)],
        {"full_scan_required": False, "full_scan_complete": None, "deterministic": False},
    )
    assert not weak_match["passed"]

    single_source_comparison = answer_quality_service.evaluate_evidence(
        "请帮我比较一下甲公司和乙公司的销售额",
        {"intent": "comparison"},
        [make_source("说明：甲公司销售额120000元；乙公司销售额76000元。")],
        {"full_scan_required": True, "full_scan_complete": True, "deterministic": False},
    )
    assert single_source_comparison["passed"]
    assert answer_quality_service._comparison_targets("哪个客户的销售额更高") == []
    generic_comparison = answer_quality_service.evaluate_evidence(
        "哪个客户的销售额更高",
        {"intent": "comparison"},
        [source],
        {"full_scan_required": True, "full_scan_complete": True, "deterministic": False},
    )
    assert generic_comparison["passed"]
    missing_comparison_target = answer_quality_service.evaluate_evidence(
        "比较甲公司和乙公司销售额",
        {"intent": "comparison"},
        [make_source("说明：甲公司销售额120000元。")],
        {"full_scan_required": True, "full_scan_complete": True, "deterministic": False},
    )
    assert not missing_comparison_target["passed"]


def check_answer_verifier() -> None:
    source = make_source("行 2：客户=甲公司；销售额=120000")
    valid = answer_quality_service.verify_answer(
        "甲公司销售额为120,000元。", "甲公司销售额是多少？", [source]
    )
    assert valid["passed"]

    scaled_number = answer_quality_service.verify_answer(
        "甲公司销售额为12万元。", "甲公司销售额是多少？", [source]
    )
    assert scaled_number["passed"]

    translated_number = answer_quality_service.verify_answer(
        "MSDC 的可学习参数 α 初始值为 0。",
        "MSDC、DACG、ACP 分别有什么作用？",
        [make_source("行 2：The learnable parameter alpha has an initial value set to zero.")],
    )
    assert translated_number["passed"]

    prefixed_entity = answer_quality_service.verify_answer(
        "对于甲公司来说，销售额是120000元。", "甲公司销售额是多少？", [source]
    )
    assert prefixed_entity["passed"]

    unsupported_number = answer_quality_service.verify_answer(
        "甲公司销售额为999元。", "甲公司销售额是多少？", [source]
    )
    assert not unsupported_number["passed"]
    assert any(issue["code"] == "unsupported_numbers" for issue in unsupported_number["issues"])

    wrong_attribution = answer_quality_service.verify_answer(
        "甲公司销售额为76000元。",
        "甲公司销售额是多少？",
        [make_source("行 2：客户=甲公司；销售额=120000\n行 3：客户=乙公司；销售额=76000")],
    )
    assert not wrong_attribution["passed"]
    assert any(issue["code"] == "unsupported_numbers" for issue in wrong_attribution["issues"])

    unsupported_entity = answer_quality_service.verify_answer(
        "乙公司销售额为120000元。", "甲公司销售额是多少？", [source]
    )
    assert not unsupported_entity["passed"]
    assert any(issue["code"] == "unsupported_entity" for issue in unsupported_entity["issues"])

    unsupported_file = answer_quality_service.verify_answer(
        "请查看 missing.xlsx，甲公司销售额为120000元。", "甲公司销售额是多少？", [source]
    )
    assert not unsupported_file["passed"]
    assert any(issue["code"] == "unsupported_source_name" for issue in unsupported_file["issues"])

    missing_evidence = answer_quality_service.verify_answer("任意答案", "问题", [])
    assert not missing_evidence["passed"]

    internal_reference = answer_quality_service.verify_answer(
        "甲公司销售额为120000元。[来源1]", "甲公司销售额是多少？", [source]
    )
    assert internal_reference["passed"]
    assert "来源1" not in internal_reference["answer"]

    deterministic = answer_quality_service.verify_answer(
        "销售额合计为196000元。", "销售额合计是多少？", [source], deterministic=True
    )
    assert deterministic["passed"]

    marker_prompt = "规则中提到【用户问题】标记。\n\n【用户问题】\n甲公司销售额是多少？"
    assert llm_service._extract_after(marker_prompt, "【用户问题】") == "甲公司销售额是多少？"


def run_chat_check(*, incomplete: bool, stream: bool = False) -> dict:
    original_data_dir = json_store.data_dir
    original_plan = query_understanding_service.plan
    original_snapshot = knowledge_metadata_service.snapshot
    original_generate = llm_service.generate_answer
    original_generate_stream = llm_service.generate_answer_stream

    plan = {
        "intent": "ranking" if incomplete else "lookup",
        "sub_queries": ["甲公司销售额"],
        "filters": {},
        "retrieval": {"top_k": None, "need_full_scan": incomplete},
    }
    source = make_source("行 2：客户=甲公司；销售额=120000")
    retrieval_state = {
        "full_scan_required": incomplete,
        "full_scan_complete": not incomplete if incomplete else None,
        "deterministic": False,
    }
    service = ChatService()
    llm_calls = []
    service._prepare_retrieval = lambda question, query_plan, top_k, filters: (  # type: ignore[method-assign]
        [source],
        None,
        retrieval_state,
    )
    query_understanding_service.plan = lambda question, context, metadata, filters: plan
    knowledge_metadata_service.snapshot = lambda question: {}

    def generate_answer(prompt, system_prompt=None):
        llm_calls.append("sync")
        return "甲公司销售额为999元。"

    def generate_answer_stream(prompt, system_prompt=None):
        llm_calls.append("stream")
        return iter(["甲公司销售额为", "999元。"])

    llm_service.generate_answer = generate_answer
    llm_service.generate_answer_stream = generate_answer_stream

    try:
        with tempfile.TemporaryDirectory(prefix="answer-quality-") as temp_dir:
            json_store.data_dir = Path(temp_dir)
            json_store.initialize()
            if stream:
                return {"events": list(service.ask_stream("甲公司销售额是多少？")), "llm_calls": llm_calls}
            response = service.ask("甲公司销售额是多少？")
            ChatResponse(**response)
            return {
                "response": response,
                "messages": service.list_messages(response["conversation_id"]),
                "llm_calls": llm_calls,
            }
    finally:
        json_store.data_dir = original_data_dir
        query_understanding_service.plan = original_plan
        knowledge_metadata_service.snapshot = original_snapshot
        llm_service.generate_answer = original_generate
        llm_service.generate_answer_stream = original_generate_stream


def check_chat_integration() -> None:
    blocked = run_chat_check(incomplete=True)
    assert "不足以支持完整计算" in blocked["response"]["answer"]
    assert not blocked["response"]["quality"]["evidence_gate"]["passed"]
    assert blocked["response"]["quality"]["answer_verifier"]["skipped"]
    assert blocked["llm_calls"] == []
    assert blocked["messages"][-1]["quality"] == blocked["response"]["quality"]

    rejected = run_chat_check(incomplete=False)
    assert "无法由当前引用证据核验" in rejected["response"]["answer"]
    assert not rejected["response"]["quality"]["answer_verifier"]["passed"]
    assert rejected["llm_calls"] == ["sync"]

    stream_result = run_chat_check(incomplete=False, stream=True)
    streamed = stream_result["events"]
    deltas = [event["data"]["text"] for event in streamed if event["event"] == "delta"]
    done = next(event["data"] for event in streamed if event["event"] == "done")
    assert deltas == ["甲公司销售额为", "999元。"]
    assert "999" not in done["answer"]
    assert not done["quality"]["answer_verifier"]["passed"]
    assert stream_result["llm_calls"] == ["stream"]


def main() -> None:
    check_evidence_gate()
    check_answer_verifier()
    check_chat_integration()
    print("answer quality self-check passed")


if __name__ == "__main__":
    main()
