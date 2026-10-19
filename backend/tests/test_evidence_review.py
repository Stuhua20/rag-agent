import copy
import json
from unittest.mock import patch

import pytest

from app.agents.budget import BudgetExceeded, RunBudget, RunCancelled
from app.agents.evidence_review import EvidenceReviewAgent, ReviewInput, ReviewUnavailable
from app.agents.evidence_review.contracts import ReviewResult
from app.agents.evidence_review.validation import answer_units, validate_result
from app.services.llm_service import llm_service


@pytest.fixture
def request_data():
    return ReviewInput.model_validate({
        "original_question": "设备怎么借？", "resolved_question": "设备怎么借？",
        "requirements": [{"id": "req-1", "query": "设备借用条件"}],
        "answer_units": [item.model_dump() for item in answer_units("经主管审批后可以借用设备。")],
        "evidence": [{"id": "chunk-a", "text": "设备借用须经主管审批，最长七天。"}],
        "rule_report": {"passed": True}, "revision_round": 0,
    })


@pytest.fixture
def good_report():
    return {"units": [{"unit_id": "unit-1", "status": "supported", "issues": [],
                       "evidence_refs": [{"evidence_id": "chunk-a", "quote": "设备借用须经主管审批"}]}],
            "tasks": [{"requirement_id": "req-1", "status": "answered", "answer_unit_ids": ["unit-1"], "reason": "已说明条件"}]}


def test_supported_paraphrase_passes_with_real_quote(request_data, good_report):
    assert validate_result(request_data, ReviewResult.model_validate(good_report))


@pytest.mark.parametrize("mutation", [
    "missing_unit", "extra_unit", "duplicate_unit", "missing_task", "extra_task", "duplicate_task",
    "unknown_quote_id", "invented_quote", "empty_refs", "unknown_task_unit", "empty_task_units",
    "duplicate_task_unit", "fact_as_non_factual", "model_passed_flag", "unknown_status", "blank_issue",
])
def test_invalid_report_is_never_approval(request_data, good_report, mutation):
    raw = copy.deepcopy(good_report)
    unit, task = raw["units"][0], raw["tasks"][0]
    if mutation == "missing_unit": raw["units"] = []
    elif mutation == "extra_unit": raw["units"].append({**unit, "unit_id": "unit-x"})
    elif mutation == "duplicate_unit": raw["units"].append(unit)
    elif mutation == "missing_task": raw["tasks"] = []
    elif mutation == "extra_task": raw["tasks"].append({**task, "requirement_id": "req-x"})
    elif mutation == "duplicate_task": raw["tasks"].append(task)
    elif mutation == "unknown_quote_id": unit["evidence_refs"][0]["evidence_id"] = "secret-chunk"
    elif mutation == "invented_quote": unit["evidence_refs"][0]["quote"] = "所有员工无条件借用"
    elif mutation == "empty_refs": unit["evidence_refs"] = []
    elif mutation == "unknown_task_unit": task["answer_unit_ids"] = ["unit-x"]
    elif mutation == "empty_task_units": task["answer_unit_ids"] = []
    elif mutation == "duplicate_task_unit": task["answer_unit_ids"] *= 2
    elif mutation == "fact_as_non_factual": unit["status"] = "non_factual"
    elif mutation == "model_passed_flag": raw["passed"] = True
    elif mutation == "unknown_status": unit["status"] = "probably_good"
    elif mutation == "blank_issue": unit.update(status="contradicted", issues=[" "])
    with patch.object(llm_service, "generate_answer", return_value=json.dumps(raw, ensure_ascii=False)):
        with pytest.raises(ReviewUnavailable):
            EvidenceReviewAgent().review(request_data, lambda _: "{review_input}")


@pytest.mark.parametrize("status", ["contradicted", "unsupported", "uncertain"])
def test_valid_negative_review_is_repairable(request_data, good_report, status):
    good_report["units"][0].update(status=status, issues=["恢复审批条件"])
    assert not validate_result(request_data, ReviewResult.model_validate(good_report))


@pytest.mark.parametrize("status", ["omitted", "uncertain"])
def test_unresolved_requirement_blocks_release(request_data, good_report, status):
    good_report["tasks"][0]["status"] = status
    assert not validate_result(request_data, ReviewResult.model_validate(good_report))


def test_gap_disclosure_without_new_fact_is_allowed(request_data, good_report):
    request_data.answer_units = answer_units("现有资料未说明维修时限。")
    good_report["units"][0].update(status="non_factual", evidence_refs=[])
    good_report["tasks"][0]["status"] = "gap_disclosed"
    assert validate_result(request_data, ReviewResult.model_validate(good_report))


def test_source_name_is_provided_as_metadata_but_cannot_authorize_quote(request_data, good_report):
    request_data.evidence[0].file_name = "设备借用制度.docx"
    good_report["units"][0]["evidence_refs"][0]["quote"] = "设备借用制度.docx"
    with pytest.raises(ValueError, match="invalid_evidence_quote"):
        validate_result(request_data, ReviewResult.model_validate(good_report))


def test_review_model_failure_and_invalid_json_are_unavailable(request_data):
    for failure in (RuntimeError("provider details must stay private"), "not-json"):
        with patch.object(llm_service, "generate_answer", **(
            {"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure}
        )):
            with pytest.raises(ReviewUnavailable, match="invalid_or_unavailable_review"):
                EvidenceReviewAgent().review(request_data, lambda _: "{review_input}")


@pytest.mark.parametrize("exception", [BudgetExceeded("llm_budget"), RunCancelled("cancelled")])
def test_budget_and_cancel_propagate(request_data, exception):
    with patch.object(llm_service, "generate_answer", side_effect=exception):
        with pytest.raises(type(exception)):
            EvidenceReviewAgent().review(request_data, lambda _: "{review_input}")


def test_answer_units_preserve_every_line_offsets_and_table_context():
    answer = "## 说明\n\n| 主体 | 条件 |\n| --- | --- |\n| 甲 | 审批 |\n\n补充说明。"
    units = answer_units(answer)
    assert len(units) == 5
    assert all(answer[item.start:item.end] == item.text for item in units)
    assert [item.structural for item in units] == [True, True, True, False, False]
    assert not answer_units("## 甲公司销售额100元")[0].structural
    for invalid in ("", "a" * 12001, "\n".join(["a"] * 101)):
        with pytest.raises(ValueError): answer_units(invalid)


def test_budget_reservation_protects_required_calls():
    budget = RunBudget(max_llm_calls=3)
    budget.reserve_llm(2)
    budget.consume("llm")
    with pytest.raises(BudgetExceeded): budget.consume("llm")
    budget.release_llm()
    budget.consume("llm")
    budget.release_llm()
    budget.consume("llm")
    assert budget.llm_calls == 3
    with pytest.raises(BudgetExceeded): budget.reserve_llm(2)
