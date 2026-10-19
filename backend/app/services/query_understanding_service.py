import json
import re
from functools import lru_cache
from pathlib import Path

from app.services.llm_service import llm_service
from app.agents.budget import BudgetExceeded, RunCancelled


PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


@lru_cache(maxsize=16)
def _load_prompt(file_path: str) -> str:
    return (PROMPTS_DIR / file_path).read_text(encoding="utf-8").strip()


class QueryUnderstandingService:
    DEFAULT_PLAN = {
        "resolved_question": "",
        "needs_clarification": False,
        "clarification_question": "",
        "intent": "lookup",
        "sub_queries": [],
        "retrieval_queries": [],
        "filters": {},
        "retrieval": {"top_k": None, "need_full_scan": False},
    }

    def plan(
        self,
        question: str,
        conversation_context: str = "无",
        metadata: dict | None = None,
        user_filters: dict | None = None,
    ) -> dict:
        """生成一次性查询规划：意图、子查询、过滤条件和检索建议。"""
        fallback = self._fallback_plan(question, metadata or {}, user_filters)
        try:
            prompt = self._build_planner_prompt(question, conversation_context, metadata or {})
            response = llm_service.generate_answer(prompt)
            plan = self._parse_json_object(response)
            return self._normalize_plan(
                plan, fallback, metadata or {}, user_filters, conversation_context=conversation_context
            )
        except (BudgetExceeded, RunCancelled):
            raise
        except Exception:
            # 即使查询规划模型不可用，也尝试用轻量翻译扩展保留跨语言召回能力。
            return self._normalize_plan(
                {}, fallback, metadata or {}, user_filters, conversation_context=conversation_context
            )

    def decompose(self, question: str, conversation_context: str = "无") -> list[str]:
        """将问题分解为多个子问题"""
        plan = self.plan(question, conversation_context)
        return plan["sub_queries"] or [question]

    def should_use_query_decomposition(self, question: str) -> bool:
        """判断是否需要调用查询分解"""
        # 简单问题特征
        simple_patterns = [
            len(question) < 10,
            not any(word in question for word in ("和", "以及", "还有", "对比", "比较", "排名", "趋势", "总计", "平均", "多少", "哪个", "哪些")),
            question.endswith(("？", "?", "吗", "呢")),
        ]
        # 如果满足多个简单特征，跳过查询分解
        if sum(simple_patterns) >= 2:
            return False
        return True

    def detect_intent(self, question: str) -> str:
        """用规则检测意图"""
        if any(word in question for word in ("排名", "最高", "最低", "最多", "最少", "前")):
            return "ranking"
        if any(word in question for word in ("对比", "相比", "比较", "哪个")):
            return "comparison"
        if any(word in question for word in ("趋势", "变化", "同比", "环比")):
            return "trend"
        if any(word in question for word in ("总计", "合计", "总和", "累计", "平均", "汇总")):
            return "summary"
        return "lookup"

    def needs_full_scan(self, question: str, plan: dict) -> bool:
        retrieval = plan.get("retrieval", {}) if isinstance(plan, dict) else {}
        if bool(retrieval.get("need_full_scan", False)):
            return True
        if plan.get("intent") in {"comparison", "ranking", "trend"}:
            return True
        if plan.get("intent") == "summary" and any(
            word in question
            for word in (
                "总计",
                "合计",
                "总和",
                "累计",
                "汇总",
                "平均",
                "均值",
                "多少条",
                "多少笔",
                "多少行",
                "多少个",
                "多少家",
                "记录数",
            )
        ):
            return True
        return any(
            word in question
            for word in (
                "总计",
                "合计",
                "总和",
                "累计",
                "汇总",
                "平均",
                "均值",
                "排名",
                "最高",
                "最多",
                "最低",
                "最少",
                "趋势",
                "同比",
                "环比",
                "对比",
                "比较",
                "多少条",
                "多少笔",
                "多少行",
                "多少个",
                "多少家",
                "记录数",
            )
        )

    def extract_filters(self, question: str, metadata: dict, user_filters: dict | None) -> dict:
        """用规则提取过滤器"""
        filters = dict(user_filters or {})
        matched_sheets = [item for item in metadata.get("sheet_names", []) if item and item in question]
        if "sheet_name" not in filters and len(matched_sheets) == 1:
            filters["sheet_name"] = matched_sheets[0]
        return filters

    def _build_planner_prompt(self, question: str, conversation_context: str, metadata: dict) -> str:
        return _load_prompt("query/planner.md").replace(
            "{question}", question
        ).replace("{conversation_context}", conversation_context).replace(
            "{metadata}", json.dumps(metadata, ensure_ascii=False, indent=2)
        )

    def _fallback_plan(self, question: str, metadata: dict, user_filters: dict | None) -> dict:
        sub_queries = [question] if not self.should_use_query_decomposition(question) else [question]
        intent = self.detect_intent(question)
        return {
            "original_question": question,
            "resolved_question": question,
            "needs_clarification": self._requires_context(question),
            "clarification_question": "",
            "intent": intent,
            "sub_queries": sub_queries,
            "retrieval_queries": self._unique_queries([question, *sub_queries]),
            "filters": self.extract_filters(question, metadata, user_filters),
            "retrieval": {"top_k": None, "need_full_scan": False},
        }

    @staticmethod
    def _requires_context(question: str) -> bool:
        """Conservative fallback for explicit references when planning cannot resolve them."""
        return bool(re.search(
            r"它们?|他们|上述|刚才|之前提到|前面提到|这个|那个|这家|那家|这些|那些|其中|同样条件"
            r"|^(?:那|那么).{0,30}(?:呢|怎么样|如何)[？?]?$"
            r"|^(?:\d{4}年)?\d{1,2}月(?:份)?呢[？?]?$"
            r"|\b(?:it|its|they|their|those|these|same|previous|above)\b|^(?:what|how) about\b",
            question,
            flags=re.IGNORECASE,
        ))

    def _normalize_plan(
        self,
        plan: dict,
        fallback: dict,
        metadata: dict,
        user_filters: dict | None,
        *,
        conversation_context: str = "无",
    ) -> dict:
        original_query = fallback["original_question"]
        resolved_question = plan.get("resolved_question")
        if not isinstance(resolved_question, str) or not resolved_question.strip() or len(resolved_question) > 2000:
            resolved_question = original_query
        else:
            resolved_question = resolved_question.strip()
        has_context = bool(conversation_context.strip() and conversation_context.strip() != "无")
        # Without history there is nothing to inherit. Keep the user's wording.
        if not has_context:
            resolved_question = original_query
        needs_clarification = plan.get("needs_clarification") is True or (
            self._requires_context(original_query)
            and (resolved_question == original_query or self._requires_context(resolved_question))
        )
        clarification = plan.get("clarification_question")
        if needs_clarification:
            return {
                **fallback,
                "needs_clarification": True,
                "clarification_question": (
                    clarification.strip()[:500] if isinstance(clarification, str) and clarification.strip()
                    else "请明确要查询的对象、时间范围和指标，或说明你指的是上一轮的哪项内容。"
                ),
            }

        intent = str(plan.get("intent") or self.detect_intent(resolved_question)).strip()
        if intent not in {"lookup", "summary", "comparison", "ranking", "trend", "unknown"}:
            intent = self.detect_intent(resolved_question)

        sub_queries = plan.get("sub_queries")
        if not isinstance(sub_queries, list):
            sub_queries = [resolved_question]
        sub_queries = [str(item).strip() for item in sub_queries if str(item).strip()]
        if not sub_queries:
            sub_queries = [resolved_question]

        planned_queries = self._normalize_query_list(plan.get("retrieval_queries"))
        base_queries = self._unique_queries([
            original_query,
            resolved_question,
            *sub_queries,
        ])
        retrieval_queries = self._unique_queries([
            *base_queries,
            *planned_queries,
        ])
        retrieval_queries = self._ensure_bilingual_queries(
            base_queries,
            retrieval_queries,
            planned_queries=planned_queries,
        )
        if not retrieval_queries:
            retrieval_queries = fallback.get("retrieval_queries") or list(sub_queries)

        filters = self._normalize_filters(plan.get("filters"), metadata, user_filters)

        retrieval = plan.get("retrieval") if isinstance(plan.get("retrieval"), dict) else {}
        top_k = retrieval.get("top_k")
        try:
            top_k = int(top_k) if top_k is not None else None
        except (TypeError, ValueError):
            top_k = None
        if top_k is not None:
            top_k = max(1, min(top_k, 10))

        return {
            "original_question": original_query,
            "resolved_question": resolved_question,
            "needs_clarification": False,
            "clarification_question": "",
            "intent": intent,
            "sub_queries": sub_queries,
            "retrieval_queries": retrieval_queries,
            "filters": filters or self.extract_filters(resolved_question, metadata, user_filters),
            "retrieval": {
                "top_k": top_k,
                "need_full_scan": bool(retrieval.get("need_full_scan", False)),
            },
        }

    def _normalize_query_list(self, queries: object) -> list[str]:
        if not isinstance(queries, list):
            return []
        return [str(query).strip() for query in queries if str(query).strip()]

    def _ensure_bilingual_queries(
        self,
        base_queries: list[str],
        retrieval_queries: list[str],
        planned_queries: list[str] | None = None,
    ) -> list[str]:
        """保留原问题，并为缺少对应语言变体的查询补充翻译。"""
        normalized_queries = self._unique_queries(retrieval_queries)
        translation_candidates = self._unique_queries(planned_queries or [])
        missing_by_language: dict[str, list[str]] = {"English": [], "Chinese": []}

        for query in self._unique_queries(base_queries):
            target_language = self._target_language(query)
            if not target_language:
                continue
            missing_by_language[target_language].append(query)

        for target_language, queries in missing_by_language.items():
            if not queries:
                continue
            available_variants = self._language_variant_count(translation_candidates, target_language)
            if available_variants >= len(queries):
                continue
            translations = self._translate_queries(queries, target_language)
            normalized_queries = self._unique_queries([*normalized_queries, *translations])

        return normalized_queries

    def _target_language(self, query: str) -> str | None:
        has_cjk = bool(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", query))
        has_latin = bool(re.search(r"[A-Za-z]", query))
        if has_cjk:
            return "English"
        if has_latin:
            return "Chinese"
        return None

    def _language_variant_count(self, candidates: list[str], target_language: str) -> int:
        count = 0
        for candidate in candidates:
            candidate = candidate.strip()
            if not candidate:
                continue
            has_cjk = bool(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", candidate))
            has_latin = bool(re.search(r"[A-Za-z]", candidate))
            if target_language == "English" and has_latin and not has_cjk:
                count += 1
            elif target_language == "Chinese" and has_cjk:
                count += 1
        return count

    def _translate_queries(self, queries: list[str], target_language: str) -> list[str]:
        """批量请求查询翻译；翻译失败时返回空列表，不影响原始检索。"""
        try:
            prompt = _load_prompt("query/translator.md").replace(
                "{target_language}", target_language
            ).replace(
                "{queries}", json.dumps(queries, ensure_ascii=False, indent=2)
            )
            translations = self._parse_json_array(llm_service.generate_answer(prompt))
        except (BudgetExceeded, RunCancelled):
            raise
        except Exception:
            return []

        if len(translations) != len(queries):
            return []

        valid_translations = []
        for query, translation in zip(queries, translations):
            text = translation.strip()
            if not text:
                return []
            # Untranslated identifiers are valid without target-language characters.
            is_identifier = re.fullmatch(r"[A-Z][A-Z0-9_-]*", text) or (
                re.fullmatch(r"[\x21-\x7e]+", text) and re.search(r"[0-9_/.:#-]", text)
            )
            if text == query.strip() and is_identifier:
                valid_translations.append(text)
                continue
            if target_language == "English" and not re.search(r"[A-Za-z]", text):
                return []
            if target_language == "Chinese" and not re.search(
                r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", text
            ):
                return []
            valid_translations.append(text)
        return valid_translations

    def _unique_queries(self, queries: list[str]) -> list[str]:
        result = []
        seen = set()
        for query in queries:
            text = str(query).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    def _normalize_filters(self, filters: dict | None, metadata: dict, user_filters: dict | None) -> dict:
        normalized = dict(user_filters or {})
        if not isinstance(filters, dict):
            return normalized

        allowed_values = {
            "sheet_name": metadata.get("sheet_names", []),
        }
        for key, allowed in allowed_values.items():
            if key in normalized:
                continue
            value = filters.get(key)
            if isinstance(value, str) and value in allowed:
                normalized[key] = value
        return normalized

    def _parse_json_array(self, text: str) -> list[str]:
        """解析 JSON 数组"""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        match = re.search(r"\[.*\]", text, flags=re.DOTALL)
        if match:
            text = match.group(0)
        data = json.loads(text)
        if isinstance(data, list):
            return [str(item).strip() for item in data if str(item).strip()]
        return []

    def _parse_json_object(self, text: str) -> dict:
        """解析 JSON 对象"""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            text = match.group(0)
        data = json.loads(text)
        return data if isinstance(data, dict) else {}


query_understanding_service = QueryUnderstandingService()
