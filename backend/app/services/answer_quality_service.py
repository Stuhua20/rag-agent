import re
from decimal import Decimal, InvalidOperation

from app.services.retrieval_service import retrieval_service


ROW_NUMBER_PATTERN = re.compile(r"(?:^|\n)\s*行\s+(\d+)：")
NUMBER_PATTERN = re.compile(
    r"(?<![0-9A-Za-z])(?P<number>[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    r"(?P<scale>万|亿)?(?P<percent>[%％]?)"
)
TEXT_NUMBER_VALUES = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "first": "1",
    "second": "2",
    "third": "3",
}
TEXT_NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z])(?:" + "|".join(sorted(TEXT_NUMBER_VALUES, key=len, reverse=True)) + r")(?![A-Za-z])",
    flags=re.IGNORECASE,
)
FILENAME_PATTERN = re.compile(
    r"(?<![\w./-])[\w().-]+\.(?:xlsx?|csv|pdf|docx?)(?!\w)",
    flags=re.IGNORECASE,
)
ENTITY_PATTERN = re.compile(
    r"[\w\u4e00-\u9fff·（）()-]{1,24}?(?:股份有限公司|有限公司|公司|集团|经销商|供应商|客户)",
    flags=re.IGNORECASE,
)
ENTITY_PREFIXES = (
    "请帮我比较一下",
    "请帮我对比一下",
    "帮我比较一下",
    "帮我对比一下",
    "请帮我",
    "比较一下",
    "对比一下",
    "分析一下",
    "查一下",
    "找一下",
    "对于",
    "关于",
    "针对",
    "根据",
    "其中",
    "比较",
    "对比",
    "分析",
    "请问",
    "帮我",
    "查询",
    "看看",
    "不同的",
    "哪家",
    "哪个",
    "哪些",
    "什么",
    "某个",
    "每个",
    "各个",
    "各家",
    "所有",
    "请",
)
GENERIC_ENTITIES = {"公司", "集团", "客户", "经销商", "供应商"}
INTERNAL_REFERENCE_PATTERNS = (
    re.compile(r"\[\s*(?:来源|source|文档)\s*\d+(?:\s*[-—~至,，、]\s*\d+)*\s*\]", re.IGNORECASE),
    re.compile(r"\b(?:chunk|chk)[_-][a-z0-9_-]+\b", re.IGNORECASE),
)


class AnswerQualityService:
    """Checks whether retrieved evidence is sufficient and whether an answer is grounded."""

    COMPLETENESS_INTENTS = {"comparison", "ranking", "trend"}
    MINIMUM_EVIDENCE_UNITS = 2

    def evaluate_evidence(
        self,
        question: str,
        query_plan: dict,
        sources: list[dict],
        retrieval_state: dict,
    ) -> dict:
        intent = str(query_plan.get("intent") or "lookup")
        full_scan_required = bool(retrieval_state.get("full_scan_required", False))
        full_scan_state = retrieval_state.get("full_scan_complete")
        full_scan_complete = None if full_scan_state is None else bool(full_scan_state)
        evidence_units = self._evidence_unit_count(sources)
        missing = []
        comparison_targets = self._comparison_targets(question) if intent == "comparison" else []
        source_text = "\n".join(str(source.get("content") or "") for source in sources).casefold()
        missing_targets = [target for target in comparison_targets if target.casefold() not in source_text]

        if not sources:
            missing.append("没有检索到可引用的知识库证据。")
        else:
            has_relevant_source = any(
                retrieval_service.is_relevant_source(source)
                for source in sources
            )
            if not has_relevant_source:
                missing.append("检索结果与问题的匹配度不足。")

        if full_scan_required and full_scan_complete is not True:
            missing.append("当前检索未能覆盖完整计算范围。")

        if missing_targets:
            missing.append("引用证据没有覆盖所有被比较对象。")

        if (
            intent in self.COMPLETENESS_INTENTS
            and evidence_units < self.MINIMUM_EVIDENCE_UNITS
            and not (intent == "comparison" and comparison_targets and not missing_targets)
        ):
            missing.append("比较、排名或趋势问题至少需要两个独立证据单元。")

        passed = not missing
        return {
            "passed": passed,
            "intent": intent,
            "reason": "证据覆盖满足当前问题的基础要求。" if passed else "；".join(missing),
            "missing": missing,
            "source_count": len(sources),
            "evidence_units": evidence_units,
            "comparison_targets": comparison_targets,
            "missing_targets": missing_targets,
            "full_scan_required": full_scan_required,
            "full_scan_complete": full_scan_complete,
            "fallback_answer": self._evidence_fallback(intent, sources, missing),
        }

    def verify_answer(
        self,
        answer: str,
        question: str,
        sources: list[dict],
        *,
        original_question: str | None = None,
        preserve_draft: bool = False,
    ) -> dict:
        verified_answer = str(answer or "").strip()
        issues = []
        # A model-resolved question describes scope; it must not authorize new facts.
        user_question = question if original_question is None else original_question

        for pattern in INTERNAL_REFERENCE_PATTERNS:
            if pattern.search(verified_answer):
                verified_answer = pattern.sub("", verified_answer)
                issues.append(
                    {
                        "code": "internal_reference_removed",
                        "severity": "warning",
                        "message": "已移除回答中的内部来源标记。",
                    }
                )

        if not verified_answer:
            issues.append(
                {
                    "code": "empty_answer",
                    "severity": "error",
                    "message": "生成结果为空。",
                }
            )

        if not sources:
            issues.append(
                {
                    "code": "missing_evidence",
                    "severity": "error",
                    "message": "没有可用于核验回答的引用证据。",
                }
            )

        unknown_filenames = self._unknown_filenames(verified_answer, sources)
        if unknown_filenames:
            issues.append(
                {
                    "code": "unsupported_source_name",
                    "severity": "error",
                    "message": "回答提到了当前引用证据中不存在的文件名。",
                    "values": unknown_filenames,
                }
            )

        unknown_entities = self._unknown_entities(verified_answer, user_question, sources)
        if unknown_entities:
            issues.append(
                {
                    "code": "unsupported_entity",
                    "severity": "error",
                    "message": "回答提到的部分组织或地域实体无法在问题或引用证据中核验。",
                    "values": unknown_entities,
                }
            )

        unsupported_numbers = []
        if sources:
            question_numbers = self._numbers_in_text(user_question)
            supported_numbers = set() if preserve_draft else set(question_numbers)
            evidence_rows = []
            for source in sources:
                supported_numbers.update(self._numbers_in_text(str(source.get("content") or "")))
                supported_numbers.update(self._numbers_in_text(str(source.get("file_name") or "")))
                supported_numbers.update(self._numbers_in_text(str(source.get("sheet_name") or "")))
                evidence_rows.extend(
                    line.strip()
                    for line in str(source.get("content") or "").splitlines()
                    if line.strip().startswith("行 ")
                )

            for line in verified_answer.splitlines():
                line_entities = [
                    normalized.casefold()
                    for entity in ENTITY_PATTERN.findall(line)
                    if (normalized := self._normalize_entity(entity))
                ]
                for value, normalized in self._number_values(line):
                    if not preserve_draft and normalized in question_numbers:
                        continue
                    if normalized not in supported_numbers:
                        unsupported_numbers.append(value)
                        continue
                    if line_entities and evidence_rows and not any(
                        normalized in self._numbers_in_text(row)
                        and any(entity in row.casefold() for entity in line_entities)
                        for row in evidence_rows
                    ):
                        unsupported_numbers.append(value)
            unsupported_numbers = list(dict.fromkeys(unsupported_numbers))
            if unsupported_numbers:
                issues.append(
                    {
                        "code": "unsupported_numbers",
                        "severity": "error",
                        "message": "回答中的部分数字无法在问题或对应实体的引用证据中核验。",
                        "values": unsupported_numbers,
                    }
                )

        passed = not any(issue["severity"] == "error" for issue in issues)
        return {
            "passed": passed,
            "issues": issues,
            "answer": verified_answer if passed or preserve_draft else self._verification_fallback(issues),
            "sanitized": any(issue["code"] == "internal_reference_removed" for issue in issues),
        }

    def _evidence_unit_count(self, sources: list[dict]) -> int:
        units = set()
        for source in sources:
            document_id = source.get("document_id") or source.get("file_name") or ""
            sheet_id = source.get("sheet_id") or source.get("sheet_name") or ""
            row_numbers = ROW_NUMBER_PATTERN.findall(str(source.get("content") or ""))
            if row_numbers:
                units.update((document_id, sheet_id, row_number) for row_number in row_numbers)
                continue

            chunk_id = source.get("chunk_id")
            if chunk_id:
                units.add((document_id, sheet_id, chunk_id))

        return len(units)

    def _evidence_fallback(self, intent: str, sources: list[dict], missing: list[str]) -> str:
        if not sources:
            return "知识库中未找到明确依据。"
        if "当前检索未能覆盖完整计算范围。" in missing:
            return "当前检索资料不足以支持完整计算。请缩小对象、时间或数据范围后重试。"
        if "引用证据没有覆盖所有被比较对象。" in missing:
            return "当前检索资料不足以支持完整比较。请补充所有比较对象的资料后重试。"
        if "比较、排名或趋势问题至少需要两个独立证据单元。" in missing:
            labels = {"comparison": "比较", "ranking": "排名", "trend": "趋势"}
            label = labels.get(intent, "分析")
            return f"当前检索资料不足以支持完整的{label}。请补充相关资料或缩小问题范围后重试。"
        return "当前检索资料不足以支持可靠回答。请补充关键词或指定文件/Sheet。"

    def _comparison_targets(self, question: str) -> list[str]:
        targets = []
        for match in ENTITY_PATTERN.findall(question):
            target = self._normalize_entity(match)
            for phrase in ("以及", "和", "与", "及", "跟"):
                if target.startswith(phrase):
                    target = target[len(phrase) :].strip()
                    break
            if target and target not in GENERIC_ENTITIES and target not in targets:
                targets.append(target)
        return targets

    def _normalize_entity(self, entity: str) -> str:
        normalized = entity.strip()
        while True:
            for prefix in ENTITY_PREFIXES:
                if normalized.startswith(prefix):
                    normalized = normalized[len(prefix) :].strip()
                    break
            else:
                break
        return normalized

    def _verification_fallback(self, issues: list[dict]) -> str:
        if any(issue.get("code") == "empty_answer" for issue in issues):
            return "模型未生成有效回答，请重试。"
        if any(issue.get("code") == "missing_evidence" for issue in issues):
            return "知识库中未找到明确依据。"
        return "检索到相关资料，但回答中有无法由当前引用证据核验的信息。为避免误答，请核对引用资料后重试。"

    def _unknown_filenames(self, answer: str, sources: list[dict]) -> list[str]:
        known_names = {
            str(source.get("file_name") or "").casefold()
            for source in sources
            if source.get("file_name")
        }
        known_tails = {name.rsplit(" ", 1)[-1] for name in known_names}
        candidates = FILENAME_PATTERN.findall(answer)
        return list(
            dict.fromkeys(
                candidate
                for candidate in candidates
                if candidate.casefold() not in known_names and candidate.casefold() not in known_tails
            )
        )

    def _unknown_entities(self, answer: str, question: str, sources: list[dict]) -> list[str]:
        supported_text = "\n".join(
            [
                question,
                *[
                    " ".join(
                        str(source.get(field) or "")
                        for field in ("content", "file_name", "sheet_name")
                    )
                    for source in sources
                ],
            ]
        ).casefold()
        return list(
            dict.fromkeys(
                entity
                for entity in ENTITY_PATTERN.findall(answer)
                if (normalized := self._normalize_entity(entity))
                and normalized.casefold() not in supported_text
            )
        )

    def _numbers_in_text(self, text: str) -> set[str]:
        return {normalized for _, normalized in self._number_values(text)}

    def _number_values(self, text: str) -> list[tuple[str, str]]:
        values = []
        for line in str(text).splitlines():
            line = re.sub(r"^\s*(?:[-*+]\s*)?\d+[.、)]\s+", "", line)
            for match in NUMBER_PATTERN.finditer(line):
                raw_value = match.group("number")
                try:
                    number = Decimal(raw_value.replace(",", ""))
                except InvalidOperation:
                    continue

                scale = match.group("scale")
                if scale == "万":
                    number *= Decimal(10_000)
                elif scale == "亿":
                    number *= Decimal(100_000_000)

                kind = "percent" if match.group("percent") else "number"
                values.append((match.group(0), f"{kind}:{number.normalize()}"))

            for match in TEXT_NUMBER_PATTERN.finditer(line):
                raw_value = match.group(0)
                number = Decimal(TEXT_NUMBER_VALUES[raw_value.casefold()])
                values.append((raw_value, f"number:{number.normalize()}"))
        return values

    def _as_float(self, value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0


answer_quality_service = AnswerQualityService()
