import json
import re

from app.agents.contracts import CoverageItem, EvidenceRequirement
from app.services.answer_quality_service import answer_quality_service
from app.services.llm_service import llm_service
from app.services.query_understanding_service import query_understanding_service


TOPICS = (
    ("付款", "支付", "结算", "payment"),
    ("交货", "交付", "供货", "delivery"),
    ("违约", "赔偿", "liability"),
    ("销售额", "销售金额", "sales", "revenue"),
    ("质保", "保修", "warranty"),
)


def target_present(target: str, text: str) -> bool:
    if not target or target.casefold() in text.casefold():
        return True
    # A question can join a location and company name; rows keep them in separate columns.
    for entity in answer_quality_service._comparison_targets(text):
        if target.casefold().endswith(entity.casefold()):
            prefix = target[:-len(entity)]
            if prefix and prefix.casefold() in text.casefold():
                return True
    return False


def requirements_for(question: str, plan: dict) -> list[dict]:
    queries = plan.get("sub_queries") or [question]
    tasks = []
    for query in queries:
        query = str(query)
        targets = [re.sub(
            r"^(?:(?:\d{4}年度?|\d{1,2}月)|今年|去年|本季度|本月|上月)", "", target,
        ) for target in answer_quality_service._comparison_targets(query)]
        for target in targets or [""]:
            # Preserve each planned goal, its dates and qualifiers while narrowing subjects.
            narrowed = query
            for other in targets:
                if other != target:
                    narrowed = narrowed.replace(other, "")
            terms = next((list(group) for group in TOPICS if any(word in narrowed.casefold() for word in group)), [])
            tasks.append(EvidenceRequirement(id=f"req-{len(tasks) + 1}", query=narrowed[:2000],
                                            target=target, terms=terms).model_dump())
    return tasks


def assess_coverage(requirements: list[dict], sources: list[dict], load_prompt) -> list[dict]:
    """Simple lookups use the existing gate; multi-goal evidence is checked separately."""
    complex_task = len(requirements) > 1
    results = []
    for requirement in requirements:
        target = requirement["target"].casefold()
        terms = requirement["terms"]
        supported = []
        for source in sources:
            text = str(source.get("content") or "").casefold()
            if not target_present(target, text):
                continue
            if terms and not any(term.casefold() in text for term in terms):
                continue
            if complex_task and not terms:
                continue  # semantic coverage needs explicit model evidence below
            supported.append(source)
        results.append(CoverageItem(
            requirement_id=requirement["id"], status="covered" if supported else "missing",
            evidence_ids=[item["chunk_id"] for item in supported],
        ).model_dump())

    if not complex_task or not sources or llm_service._get_config()["mock"]:
        return results
    prompt = load_prompt("agent/evidence_coverage.md").replace(
        "{requirements}", json.dumps(requirements, ensure_ascii=False)
    ).replace("{evidence}", json.dumps([
        {"id": source["chunk_id"], "text": source["content"]} for source in sources
    ], ensure_ascii=False))
    try:
        raw = query_understanding_service._parse_json_object(llm_service.generate_answer(prompt))
        items = {item["requirement_id"]: CoverageItem.model_validate(item) for item in raw.get("items", [])}
        by_id = {item["chunk_id"]: item for item in sources}
        checked = []
        for requirement in requirements:
            item = items.get(requirement["id"])
            if item is None:
                item = CoverageItem(requirement_id=requirement["id"], status="uncertain")
            if item.status == "covered":
                valid = [by_id[key] for key in item.evidence_ids if key in by_id]
                quote = re.sub(r"\s+", "", item.quote)
                if (requirement["terms"] and not any(term.casefold() in item.quote.casefold() for term in requirement["terms"])) or len(quote) < 6 or not any(
                    quote in re.sub(r"\s+", "", source["content"])
                    and target_present(requirement["target"], source["content"])
                    for source in valid
                ) or len(valid) != len(item.evidence_ids):
                    item = CoverageItem(requirement_id=requirement["id"], status="uncertain")
            checked.append(item.model_dump())
        return checked
    except Exception:
        # Model unavailability never silently approves multi-goal semantic coverage.
        return [CoverageItem(requirement_id=item["id"], status="uncertain").model_dump() for item in requirements]
