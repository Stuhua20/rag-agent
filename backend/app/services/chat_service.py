import json
from collections.abc import Generator
from functools import lru_cache
from threading import RLock

from fastapi import HTTPException

from app.schemas.conversation import DocumentScope
from app.core.config import settings
from pathlib import Path

from app.services.answer_quality_service import answer_quality_service
from app.services.conversation_context_service import conversation_context_service
from app.services.json_store_service import json_store
from app.services.knowledge_metadata_service import knowledge_metadata_service
from app.services.llm_service import llm_service
from app.services.query_understanding_service import query_understanding_service
from app.services.retrieval_service import retrieval_service
from app.services.retrieval_index_service import retrieval_index_service
from app.utils.id_utils import new_id
from app.utils.time_utils import utc_now_iso


PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


@lru_cache(maxsize=16)
def _load_prompt(file_path: str) -> str:
    return (PROMPTS_DIR / file_path).read_text(encoding="utf-8").strip()


class ChatService:
    def __init__(self) -> None:
        self._agent_runtime = None
        self._run_store = None
        from app.services.run_coordinator import RunCoordinator
        self.coordinator = RunCoordinator()
        self._runtime_lock = RLock()

    def run_store(self):
        with self._runtime_lock:
            if self._run_store is None:
                from app.services.agent_run_store import AgentRunStore
                self._run_store = AgentRunStore(json_store.data_dir / "agent")
            return self._run_store

    def agent_runtime(self):
        with self._runtime_lock:
            if self._agent_runtime is None:
                from app.agents.knowledge_qa.runtime import KnowledgeQARuntime
                self._agent_runtime = KnowledgeQARuntime(self)
            return self._agent_runtime

    def close(self) -> None:
        for stream in list(self.coordinator.streams.values()):
            stream.close()
        if self._agent_runtime is not None:
            self._agent_runtime.close()
            self._agent_runtime = None
        if self._run_store is not None:
            self._run_store.close()
            self._run_store = None

    def ask(self, question: str, conversation_id: str | None = None, top_k: int | None = None,
            filters: dict | None = None, expected_scope_revision: int | None = None,
            _conversation: dict | None = None) -> dict:
        if settings.chat_runtime == "legacy":
            conversation = _conversation or self.prepare_conversation(conversation_id, question, expected_scope_revision)
            return self._ask_legacy(question, conversation_id, top_k, filters, expected_scope_revision, conversation)
        stream = self.ask_stream(question, conversation_id, top_k, filters, expected_scope_revision, _conversation)
        try:
            for event in stream:
                if event["event"] == "error":
                    raise HTTPException(status_code=500, detail=event["data"]["message"])
                if event["event"] == "done":
                    return event["data"]
            raise HTTPException(status_code=500, detail="Agent 未返回完整结果。")
        finally:
            stream.close()

    def ask_stream(self, question: str, conversation_id: str | None = None, top_k: int | None = None,
                   filters: dict | None = None, expected_scope_revision: int | None = None,
                   _conversation: dict | None = None):
        conversation = _conversation or self.prepare_conversation(conversation_id, question, expected_scope_revision)
        if settings.chat_runtime == "legacy":
            return self._ask_stream_legacy(question, conversation_id, top_k, filters, expected_scope_revision, conversation)
        return self.agent_runtime().open_stream(question, conversation, top_k, filters)

    def _ask_legacy(
        self,
        question: str,
        conversation_id: str | None = None,
        top_k: int | None = None,
        filters: dict | None = None,
        expected_scope_revision: int | None = None,
        _conversation: dict | None = None,
    ) -> dict:
        question = question.strip()
        retrieval_version = retrieval_index_service.version()
        conversation = _conversation or self.prepare_conversation(conversation_id, question, expected_scope_revision)
        scope = conversation.get("document_scope", {"mode": "all", "document_ids": []})
        filters = {key: value for key, value in (filters or {}).items() if key != "document_ids"}
        if scope["mode"] == "selected":
            filters["document_ids"] = scope["document_ids"]
        conversation_context = conversation_context_service.build_context(
            self.list_messages(conversation["id"]), scope_revision=conversation.get("scope_revision", 0),
        )
        self._add_message(conversation["id"], "user", question, [], scope_context=conversation)

        metadata = (
            knowledge_metadata_service.snapshot(question, document_ids=scope["document_ids"])
            if scope["mode"] == "selected" else knowledge_metadata_service.snapshot(question)
        )
        query_plan = {**query_understanding_service.plan(question, conversation_context, metadata, filters),
                      "document_scope": scope}
        if query_plan.get("needs_clarification"):
            return self._clarification_response(conversation, question, query_plan)
        resolved_question = query_plan.get("resolved_question") or question
        sources, retrieval_state = self._prepare_retrieval(
            resolved_question, query_plan, top_k, filters
        )
        evidence_report = answer_quality_service.evaluate_evidence(
            resolved_question, query_plan, sources, retrieval_state
        )
        evidence_fallback = evidence_report.pop("fallback_answer")

        if evidence_report["passed"]:
            draft_answer = llm_service.generate_answer(
                self._build_prompt(
                    question, sources, query_plan, conversation_context, evidence_report=evidence_report,
                ),
                system_prompt=_load_prompt("system/base.md"),
            )
            verification = answer_quality_service.verify_answer(
                draft_answer,
                resolved_question,
                sources,
                original_question=question,
            )
            answer = verification.pop("answer")
            verifier_report = verification
        else:
            answer = self._no_source_answer(conversation) if not sources else evidence_fallback
            verifier_report = {
                "passed": None,
                "skipped": True,
                "reason": "Evidence Gate 未通过，没有生成模型答案。",
                "issues": [],
            }

        quality = {
            "query_understanding": self._question_trace(question, query_plan),
            "evidence_gate": evidence_report,
            "answer_verifier": verifier_report,
            "evidence_review": {"mode": "legacy", "status": "skipped", "passed": None, "reason": "legacy"},
        }
        with json_store._lock:
            retrieval_index_service.assert_current(retrieval_version)
            self._add_message(conversation["id"], "assistant", answer, sources, quality, scope_context=conversation)
        self._touch_conversation(conversation["id"])

        return {"conversation_id": conversation["id"], "answer": answer, "sources": sources, "quality": quality}

    def _ask_stream_legacy(
        self,
        question: str,
        conversation_id: str | None = None,
        top_k: int | None = None,
        filters: dict | None = None,
        expected_scope_revision: int | None = None,
        _conversation: dict | None = None,
    ) -> Generator[dict, None, None]:
        question = question.strip()
        retrieval_version = retrieval_index_service.version()
        conversation = _conversation or self.prepare_conversation(conversation_id, question, expected_scope_revision)
        scope = conversation.get("document_scope", {"mode": "all", "document_ids": []})
        filters = {key: value for key, value in (filters or {}).items() if key != "document_ids"}
        if scope["mode"] == "selected":
            filters["document_ids"] = scope["document_ids"]
        conversation_context = conversation_context_service.build_context(
            self.list_messages(conversation["id"]), scope_revision=conversation.get("scope_revision", 0),
        )
        self._add_message(conversation["id"], "user", question, [], scope_context=conversation)

        metadata = (
            knowledge_metadata_service.snapshot(question, document_ids=scope["document_ids"])
            if scope["mode"] == "selected" else knowledge_metadata_service.snapshot(question)
        )
        query_plan = {**query_understanding_service.plan(question, conversation_context, metadata, filters),
                      "document_scope": scope}
        if query_plan.get("needs_clarification"):
            result = self._clarification_response(conversation, question, query_plan)
            yield {"event": "sources", "data": {"conversation_id": conversation["id"], "sources": []}}
            yield {"event": "delta", "data": {"text": result["answer"]}}
            yield {"event": "done", "data": {
                "conversation_id": conversation["id"], "answer": result["answer"], "quality": result["quality"],
            }}
            return
        resolved_question = query_plan.get("resolved_question") or question
        sources, retrieval_state = self._prepare_retrieval(
            resolved_question, query_plan, top_k, filters
        )

        yield {
            "event": "sources",
            "data": {"conversation_id": conversation["id"], "sources": sources},
        }

        evidence_report = answer_quality_service.evaluate_evidence(
            resolved_question, query_plan, sources, retrieval_state
        )
        evidence_fallback = evidence_report.pop("fallback_answer")
        answer_chunks: list[str] = []
        if not evidence_report["passed"]:
            answer = self._no_source_answer(conversation) if not sources else evidence_fallback
            verifier_report = {
                "passed": None,
                "skipped": True,
                "reason": "Evidence Gate 未通过，没有生成模型答案。",
                "issues": [],
            }
        else:
            prompt = self._build_prompt(
                question, sources, query_plan, conversation_context, evidence_report=evidence_report,
            )
            for text in llm_service.generate_answer_stream(prompt, system_prompt=_load_prompt("system/base.md")):
                if text:
                    answer_chunks.append(text)
                    yield {"event": "delta", "data": {"text": text}}
            draft_answer = "".join(answer_chunks)
            verification = answer_quality_service.verify_answer(
                draft_answer,
                resolved_question,
                sources,
                original_question=question,
            )
            answer = verification.pop("answer")
            verifier_report = verification

        quality = {
            "query_understanding": self._question_trace(question, query_plan),
            "evidence_gate": evidence_report,
            "answer_verifier": verifier_report,
            "evidence_review": {"mode": "legacy", "status": "skipped", "passed": None, "reason": "legacy"},
        }
        # Streamed text is a draft; done.answer below replaces it with the verified result.
        if not answer_chunks:
            yield {"event": "delta", "data": {"text": answer}}

        with json_store._lock:
            retrieval_index_service.assert_current(retrieval_version)
            self._add_message(conversation["id"], "assistant", answer, sources, quality, scope_context=conversation)
        self._touch_conversation(conversation["id"])

        yield {
            "event": "done",
            "data": {"conversation_id": conversation["id"], "answer": answer, "quality": quality},
        }

    @staticmethod
    def _question_trace(question: str, query_plan: dict) -> dict:
        """Persist interpretation separately from the user's message and evidence."""
        return {
            "original_question": question,
            "resolved_question": query_plan.get("resolved_question") or question,
            "retrieval_queries": query_plan.get("retrieval_queries") or query_plan.get("sub_queries") or [question],
            "needs_clarification": bool(query_plan.get("needs_clarification", False)),
            "clarification_question": query_plan.get("clarification_question") or "",
        }

    def _clarification_response(self, conversation: dict, question: str, query_plan: dict) -> dict:
        answer = query_plan["clarification_question"]
        reason = "问题中的指代或省略条件尚未明确，等待用户补充。"
        quality = {
            "query_understanding": self._question_trace(question, query_plan),
            "evidence_gate": {"passed": False, "skipped": True, "reason": reason, "source_count": 0},
            "answer_verifier": {"passed": None, "skipped": True, "reason": reason, "issues": []},
            "evidence_review": {"mode": "legacy", "status": "skipped", "passed": None, "reason": "legacy"},
        }
        self._add_message(conversation["id"], "assistant", answer, [], quality, scope_context=conversation)
        self._touch_conversation(conversation["id"])
        return {"conversation_id": conversation["id"], "answer": answer, "sources": [], "quality": quality}

    def _prepare_retrieval(
        self,
        question: str,
        query_plan: dict,
        top_k: int | None,
        filters: dict | None,
    ) -> tuple[list[dict], dict]:
        question = query_plan.get("resolved_question") or question
        sub_queries = query_plan.get("sub_queries") or [question]
        retrieval_queries = query_plan.get("retrieval_queries") or sub_queries
        intent = query_plan.get("intent", "lookup")
        merged_filters = {**(query_plan.get("filters") or filters or {})}
        # Document scope is enforced by the caller, never by the model's query plan.
        merged_filters.pop("document_ids", None)
        if filters is not None and "document_ids" in filters:
            merged_filters["document_ids"] = filters["document_ids"]
        planned_top_k = query_plan.get("retrieval", {}).get("top_k")
        dynamic_top_k = top_k or planned_top_k or self._determine_top_k(intent, top_k)

        full_scan = query_understanding_service.needs_full_scan(question, query_plan)
        sources = retrieval_service.search_multiple(
            retrieval_queries,
            top_k=dynamic_top_k,
            filters=merged_filters,
            full_scan=full_scan,
        )
        if full_scan and len(sources) > retrieval_service.full_scan_max_chunks():
            return sources[:dynamic_top_k], {
                "full_scan_required": True,
                "full_scan_complete": False,
            }
        return sources, {
            "full_scan_required": full_scan,
            "full_scan_complete": True if full_scan else None,
        }

    def _determine_top_k(self, intent: str, default_top_k: int | None) -> int:
        """根据意图动态确定检索数量"""
        base = default_top_k if default_top_k is not None else retrieval_service.top_k()

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

    def create_conversation(self, title: str | None = None, document_scope: dict | None = None) -> dict:
        scope = DocumentScope.model_validate(document_scope or {}).model_dump()
        self._validate_scope_documents(scope)
        now = utc_now_iso()
        conversation = {
            "id": new_id("conv"),
            "title": title or "新对话",
            "document_scope": scope,
            "scope_revision": 0,
            "created_at": now,
            "updated_at": now,
        }
        return json_store.add_item("conversations.json", conversation)

    @staticmethod
    def _invalid_scope_ids(scope: dict) -> list[str]:
        if scope["mode"] == "all":
            return []
        indexed_ids = {
            item["id"] for item in json_store.list_items("documents.json") if item.get("status") == "indexed"
        }
        return [item for item in scope["document_ids"] if item not in indexed_ids]

    def _validate_scope_documents(self, scope: dict) -> None:
        if self._invalid_scope_ids(scope):
            raise HTTPException(status_code=409, detail="所选文档已删除或尚未完成入库，请重新选择检索文档。")

    def get_conversation(self, conversation_id: str) -> dict:
        conversation = json_store.get_item("conversations.json", conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="会话不存在。")
        scope = DocumentScope.model_validate(conversation.get("document_scope") or {}).model_dump()
        return {**conversation, "document_scope": scope, "scope_revision": conversation.get("scope_revision", 0),
                "invalid_document_ids": self._invalid_scope_ids(scope)}

    def update_document_scope(self, conversation_id: str, scope: dict, expected_revision: int) -> dict:
        scope = DocumentScope.model_validate(scope).model_dump()
        current = self.get_conversation(conversation_id)
        if current["scope_revision"] != expected_revision:
            raise HTTPException(status_code=409, detail="会话检索范围已在其他窗口更新，请刷新范围后重试。")
        self._validate_scope_documents(scope)
        if current["document_scope"] == scope:
            return current
        raw = json_store.get_item("conversations.json", conversation_id)
        if raw is None or raw.get("scope_revision", 0) != expected_revision:
            raise HTTPException(status_code=409, detail="会话已更新，请刷新后重试。")
        updated = json_store.update_item(
            "conversations.json", conversation_id,
            {"document_scope": scope, "scope_revision": expected_revision + 1, "updated_at": utc_now_iso()},
            expected={"scope_revision": raw.get("scope_revision")},
        )
        if updated is None:
            raise HTTPException(status_code=409, detail="会话已更新，请刷新后重试。")
        return {**updated, "invalid_document_ids": []}

    def rename_conversation(self, conversation_id: str, title: str) -> dict:
        updated = json_store.update_item("conversations.json", conversation_id, {"title": title})
        if updated is None:
            raise HTTPException(status_code=404, detail="会话不存在，可能已被删除。")
        return updated

    def prepare_conversation(
        self, conversation_id: str | None, question: str, expected_revision: int | None = None,
    ) -> dict:
        conversation = self._get_or_create_conversation(conversation_id, question)
        if expected_revision is not None and expected_revision != conversation.get("scope_revision", 0):
            raise HTTPException(status_code=409, detail="会话检索范围已在其他窗口更新，请刷新范围后重试。")
        self._validate_scope_documents(conversation.get("document_scope", {"mode": "all", "document_ids": []}))
        return conversation

    @staticmethod
    def _no_source_answer(conversation: dict) -> str:
        if conversation.get("document_scope", {}).get("mode") == "selected":
            return "所选文档中未找到明确依据。"
        return _load_prompt("rag/no_source.md")

    def list_messages(self, conversation_id: str) -> list[dict]:
        return [
            message
            for message in json_store.list_items("messages.json")
            if message.get("conversation_id") == conversation_id
        ]

    def delete_conversation(self, conversation_id: str) -> bool:
        self.coordinator.cancel(conversation_id)
        if self._agent_runtime is not None:
            self._agent_runtime.cancel_conversation(conversation_id)
        deleted = self._delete_conversation_locked(conversation_id)
        if self._run_store and conversation_id not in self.coordinator.active:
            self._run_store.delete_conversation(conversation_id)
        return deleted

    def _delete_conversation_locked(self, conversation_id: str) -> bool:
        with json_store._lock:
            return self._delete_conversation_records(conversation_id)

    def _delete_conversation_records(self, conversation_id: str) -> bool:
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
            raise HTTPException(status_code=404, detail="会话不存在，请新建会话。")
        title = question[:30] if question else "新对话"
        return self.create_conversation(title)

    def _add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        sources: list[dict],
        quality: dict | None = None,
        *, scope_context: dict | None = None, run_id: str | None = None, status: str | None = None,
    ) -> dict:
        message = {
            "id": new_id("msg"),
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "sources": sources,
            "created_at": utc_now_iso(),
        }
        if scope_context is not None:
            message["document_scope"] = scope_context.get("document_scope", {"mode": "all", "document_ids": []})
            message["scope_revision"] = scope_context.get("scope_revision", 0)
        if quality is not None:
            message["quality"] = quality
        if run_id is not None:
            message["run_id"] = run_id
            message["status"] = status
            return json_store.add_run_message(message)
        return json_store.add_item("messages.json", message)

    def _touch_conversation(self, conversation_id: str) -> None:
        json_store.update_item("conversations.json", conversation_id, {"updated_at": utc_now_iso()})

    def _build_prompt(
        self,
        question: str,
        sources: list[dict],
        query_plan: dict | None = None,
        conversation_context: str = "无",
        *,
        evidence_report: dict | None = None,
    ) -> str:
        context = "\n\n".join(self._format_source(index, source) for index, source in enumerate(sources, start=1))
        template = _load_prompt("rag/answer.md")
        return (
            template.replace("{conversation_context}", conversation_context)
            .replace("{query_plan}", self._format_query_plan(query_plan))
            .replace("{resolved_question}", (query_plan or {}).get("resolved_question") or question)
            .replace("{evidence_report}", json.dumps(evidence_report or {}, ensure_ascii=False, indent=2))
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
