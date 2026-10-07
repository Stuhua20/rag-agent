import json
from collections.abc import Generator
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.services.answer_quality_service import answer_quality_service
from app.services.conversation_context_service import conversation_context_service
from app.services.json_store_service import json_store
from app.services.knowledge_metadata_service import knowledge_metadata_service
from app.services.llm_service import llm_service
from app.services.query_understanding_service import query_understanding_service
from app.services.retrieval_service import retrieval_service
from app.services.table_analysis_service import table_analysis_service
from app.utils.id_utils import new_id
from app.utils.time_utils import utc_now_iso


PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


@lru_cache(maxsize=16)
def _load_prompt(file_path: str) -> str:
    return (PROMPTS_DIR / file_path).read_text(encoding="utf-8").strip()


class ChatService:
    def ask(
        self,
        question: str,
        conversation_id: str | None = None,
        top_k: int | None = None,
        filters: dict | None = None,
    ) -> dict:
        question = question.strip()
        conversation = self._get_or_create_conversation(conversation_id, question)
        conversation_context = conversation_context_service.build_context(self.list_messages(conversation["id"]))
        self._add_message(conversation["id"], "user", question, [])

        metadata = knowledge_metadata_service.snapshot(question)
        query_plan = query_understanding_service.plan(question, conversation_context, metadata, filters)
        sources, deterministic_answer, retrieval_state = self._prepare_retrieval(
            question, query_plan, top_k, filters
        )
        evidence_report = answer_quality_service.evaluate_evidence(
            question, query_plan, sources, retrieval_state
        )
        evidence_fallback = evidence_report.pop("fallback_answer")

        if evidence_report["passed"]:
            draft_answer = (
                deterministic_answer
                if deterministic_answer is not None
                else llm_service.generate_answer(
                    self._build_prompt(question, sources, query_plan, conversation_context),
                    system_prompt=_load_prompt("system/base.md"),
                )
            )
            verification = answer_quality_service.verify_answer(
                draft_answer,
                question,
                sources,
                deterministic=deterministic_answer is not None,
            )
            answer = verification.pop("answer")
            verifier_report = verification
        else:
            answer = _load_prompt("rag/no_source.md") if not sources else evidence_fallback
            verifier_report = {
                "passed": None,
                "skipped": True,
                "reason": "Evidence Gate 未通过，没有生成模型答案。",
                "issues": [],
            }

        quality = {"evidence_gate": evidence_report, "answer_verifier": verifier_report}
        self._add_message(conversation["id"], "assistant", answer, sources, quality)
        self._touch_conversation(conversation["id"])

        return {"conversation_id": conversation["id"], "answer": answer, "sources": sources, "quality": quality}

    def ask_stream(
        self,
        question: str,
        conversation_id: str | None = None,
        top_k: int | None = None,
        filters: dict | None = None,
    ) -> Generator[dict, None, None]:
        question = question.strip()
        conversation = self._get_or_create_conversation(conversation_id, question)
        conversation_context = conversation_context_service.build_context(self.list_messages(conversation["id"]))
        self._add_message(conversation["id"], "user", question, [])

        metadata = knowledge_metadata_service.snapshot(question)
        query_plan = query_understanding_service.plan(question, conversation_context, metadata, filters)
        sources, deterministic_answer, retrieval_state = self._prepare_retrieval(
            question, query_plan, top_k, filters
        )

        yield {
            "event": "sources",
            "data": {"conversation_id": conversation["id"], "sources": sources},
        }

        evidence_report = answer_quality_service.evaluate_evidence(
            question, query_plan, sources, retrieval_state
        )
        evidence_fallback = evidence_report.pop("fallback_answer")
        if not evidence_report["passed"]:
            answer = _load_prompt("rag/no_source.md") if not sources else evidence_fallback
            verifier_report = {
                "passed": None,
                "skipped": True,
                "reason": "Evidence Gate 未通过，没有生成模型答案。",
                "issues": [],
            }
        else:
            if deterministic_answer is not None:
                draft_answer = deterministic_answer
            else:
                prompt = self._build_prompt(question, sources, query_plan, conversation_context)
                draft_answer = "".join(
                    llm_service.generate_answer_stream(prompt, system_prompt=_load_prompt("system/base.md"))
                )
            verification = answer_quality_service.verify_answer(
                draft_answer,
                question,
                sources,
                deterministic=deterministic_answer is not None,
            )
            answer = verification.pop("answer")
            verifier_report = verification

        quality = {"evidence_gate": evidence_report, "answer_verifier": verifier_report}
        yield {"event": "delta", "data": {"text": answer}}

        self._add_message(conversation["id"], "assistant", answer, sources, quality)
        self._touch_conversation(conversation["id"])

        yield {
            "event": "done",
            "data": {"conversation_id": conversation["id"], "answer": answer, "quality": quality},
        }

    def _prepare_retrieval(
        self,
        question: str,
        query_plan: dict,
        top_k: int | None,
        filters: dict | None,
    ) -> tuple[list[dict], str | None, dict]:
        sub_queries = query_plan.get("sub_queries") or [question]
        retrieval_queries = query_plan.get("retrieval_queries") or sub_queries
        intent = query_plan.get("intent", "lookup")
        merged_filters = query_plan.get("filters") or filters or {}
        planned_top_k = query_plan.get("retrieval", {}).get("top_k")
        dynamic_top_k = top_k or planned_top_k or self._determine_top_k(intent, top_k)

        full_scan = query_understanding_service.needs_full_scan(question, query_plan)
        analysis = table_analysis_service.analyze(
            question,
            intent,
            merged_filters,
            query_variants=retrieval_queries,
        )
        if analysis:
            sources = retrieval_service.sources_for_chunk_ids(analysis["chunk_ids"], limit=dynamic_top_k)
            return sources, analysis["answer"], {
                "full_scan_required": True,
                "full_scan_complete": True,
                "deterministic": True,
            }

        sources = retrieval_service.search_multiple(
            retrieval_queries,
            top_k=dynamic_top_k,
            filters=merged_filters,
            full_scan=full_scan,
        )
        if full_scan and len(sources) > retrieval_service.full_scan_max_chunks():
            return sources[:dynamic_top_k], None, {
                "full_scan_required": True,
                "full_scan_complete": False,
                "deterministic": False,
            }
        return sources, None, {
            "full_scan_required": full_scan,
            "full_scan_complete": True if full_scan else None,
            "deterministic": False,
        }

    def _determine_top_k(self, intent: str, default_top_k: int | None) -> int:
        """根据意图动态确定检索数量"""
        base = default_top_k or settings.default_top_k

        # 复杂问题需要更多结果
        if intent == "ranking":
            return min(base + 3, 10)
        if intent == "summary":
            return min(base + 2, 8)

        # 简单查询问题
        if intent == "lookup":
            return max(base - 2, 2)

        # 趋势或对比问题
        if intent in ("trend", "comparison"):
            return min(base + 2, 8)

        return base

    def list_conversations(self) -> list[dict]:
        conversations = json_store.list_items("conversations.json")
        return sorted(conversations, key=lambda item: item.get("updated_at", ""), reverse=True)

    def create_conversation(self, title: str | None = None) -> dict:
        now = utc_now_iso()
        conversation = {
            "id": new_id("conv"),
            "title": title or "新对话",
            "created_at": now,
            "updated_at": now,
        }
        return json_store.add_item("conversations.json", conversation)

    def list_messages(self, conversation_id: str) -> list[dict]:
        return [
            message
            for message in json_store.list_items("messages.json")
            if message.get("conversation_id") == conversation_id
        ]

    def delete_conversation(self, conversation_id: str) -> bool:
        deleted = json_store.delete_item("conversations.json", conversation_id)
        if not deleted:
            return False
        messages = [
            message
            for message in json_store.list_items("messages.json")
            if message.get("conversation_id") != conversation_id
        ]
        json_store.write_json("messages.json", messages)
        return True

    def _get_or_create_conversation(self, conversation_id: str | None, question: str) -> dict:
        if conversation_id:
            conversation = json_store.get_item("conversations.json", conversation_id)
            if conversation:
                return conversation
        title = question[:30] if question else "新对话"
        return self.create_conversation(title)

    def _add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        sources: list[dict],
        quality: dict | None = None,
    ) -> dict:
        message = {
            "id": new_id("msg"),
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "sources": sources,
            "created_at": utc_now_iso(),
        }
        if quality is not None:
            message["quality"] = quality
        return json_store.add_item("messages.json", message)

    def _touch_conversation(self, conversation_id: str) -> None:
        json_store.update_item("conversations.json", conversation_id, {"updated_at": utc_now_iso()})

    def _build_prompt(
        self,
        question: str,
        sources: list[dict],
        query_plan: dict | None = None,
        conversation_context: str = "无",
    ) -> str:
        context = "\n\n".join(self._format_source(index, source) for index, source in enumerate(sources, start=1))
        template = _load_prompt("rag/answer.md")
        return (
            template.replace("{conversation_context}", conversation_context)
            .replace("{query_plan}", self._format_query_plan(query_plan))
            .replace("{context}", context)
            .replace("{question}", question)
        )

    def _format_query_plan(self, query_plan: dict | None) -> str:
        if not query_plan:
            return "无"
        return json.dumps(query_plan, ensure_ascii=False, indent=2)

    def _format_source(self, index: int, source: dict) -> str:
        return f"""[来源{index}]
文件名：{source.get("file_name", "")}
Sheet：{source.get("sheet_name", "")}
行号：{source.get("row_start")}-{source.get("row_end")}
相关度：{source.get("score", 0)}
内容：{source.get("content", "")}"""


chat_service = ChatService()
