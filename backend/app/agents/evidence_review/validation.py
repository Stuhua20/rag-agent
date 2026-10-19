import re

from app.agents.evidence_review.contracts import AnswerUnit, ReviewInput, ReviewResult


def answer_units(answer: str) -> list[AnswerUnit]:
    """Keep every nonblank line and its offsets, including Markdown table context."""
    if len(answer) > 12000:
        raise ValueError("answer_too_long")
    result = []
    offset = 0
    lines = answer.splitlines(keepends=True)
    for index, line in enumerate(lines):
        text = line.strip()
        if text:
            start = offset + len(line) - len(line.lstrip())
            table_separator = bool(re.fullmatch(r"\|?[\s:|-]+\|?", text)) and "---" in text
            table_header = index + 1 < len(lines) and bool(re.fullmatch(
                r"\s*\|?[\s:|-]+\|?\s*", lines[index + 1],
            )) and "---" in lines[index + 1] and "|" in text
            result.append(AnswerUnit(
                id=f"unit-{len(result) + 1}", text=text, start=start, end=start + len(text),
                structural=table_separator or table_header or bool(re.fullmatch(
                    r"#{1,6}\s+(?:答案|说明|注意事项|资料缺口|结论|回答|对比|适用条件)", text,
                )),
            ))
        offset += len(line)
    if not result or len(result) > 100:
        raise ValueError("answer_unit_limit")
    return result


def _exact_ids(actual: list[str], expected: list[str]) -> None:
    if len(actual) != len(set(actual)) or len(expected) != len(set(expected)) or set(actual) != set(expected):
        raise ValueError("incomplete_or_duplicate_ids")


def validate_result(request: ReviewInput, result: ReviewResult) -> bool:
    """Validate references and coverage before deriving the release decision."""
    if sum(len(item.text) for item in request.evidence) > 24000:
        raise ValueError("evidence_too_long")
    _exact_ids([item.unit_id for item in result.units], [item.id for item in request.answer_units])
    _exact_ids([item.requirement_id for item in result.tasks], [item.id for item in request.requirements])
    evidence = {item.id: item.text for item in request.evidence}
    if len(evidence) != len(request.evidence):
        raise ValueError("duplicate_evidence")
    units = {item.id: item for item in request.answer_units}
    reviews = {item.unit_id: item for item in result.units}
    for task in result.tasks:
        if len(task.answer_unit_ids) != len(set(task.answer_unit_ids)) or not set(task.answer_unit_ids) <= units.keys():
            raise ValueError("invalid_task_units")
        if task.status in {"answered", "gap_disclosed"} and not task.answer_unit_ids:
            raise ValueError("missing_task_units")
        if task.status == "answered" and not any(reviews[key].status != "non_factual" for key in task.answer_unit_ids):
            raise ValueError("task_without_supported_answer")
    for item in result.units:
        if item.status == "supported" and not item.evidence_refs:
            raise ValueError("missing_evidence_refs")
        for ref in item.evidence_refs:
            quote = re.sub(r"\s+", "", ref.quote)
            if ref.evidence_id not in evidence or not quote or quote not in re.sub(r"\s+", "", evidence[ref.evidence_id]):
                raise ValueError("invalid_evidence_quote")
        if item.status == "non_factual" and not units[item.unit_id].structural:
            # Only an explicit disclosure of missing information can bypass factual support.
            gap = any(task.status == "gap_disclosed" and item.unit_id in task.answer_unit_ids for task in result.tasks)
            if not gap or not re.search(r"未(?:提供|说明|找到|提及)|无法(?:确定|核实)|资料不足|存在冲突", units[item.unit_id].text):
                raise ValueError("invalid_non_factual_unit")
        if item.status in {"contradicted", "unsupported", "uncertain"} and not any(issue.strip() for issue in item.issues):
            raise ValueError("missing_review_issue")
    return (request.rule_report.get("passed") is True
            and all(item.status in {"supported", "non_factual"} and not item.issues for item in result.units)
            and all(item.status in {"answered", "gap_disclosed"} for item in result.tasks))
