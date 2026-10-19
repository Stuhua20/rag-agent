import json
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
from typing import Any

from fastapi import HTTPException
from langgraph.config import get_stream_writer

from app.agents.budget import RunBudget, RunCancelled
from app.core.config import settings
from app.services.json_store_service import json_store
from app.services.agent_run_store import AgentRunStore
from app.utils.id_utils import new_id


logger = logging.getLogger(__name__)


class DocumentChanged(RuntimeError):
    pass


@dataclass
class RunContext:
    service: Any
    conversation: dict
    documents: dict[str, str]
    budget: RunBudget
    filters: dict
    top_k: int | None
    history: list[dict] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    sources_emitted: bool = False
    delta_emitted: bool = False

    def check(self, *, check_budget: bool = True) -> None:
        if self.budget.cancelled.is_set():
            raise RunCancelled("运行已取消。")
        if check_budget:
            self.budget.check()
        with json_store._lock:
            if json_store.get_item("conversations.json", self.conversation["id"]) is None:
                raise RunCancelled("会话已删除。")
            current = {item["id"]: json.dumps(item, sort_keys=True, ensure_ascii=False)
                       for item in json_store.list_items("documents.json") if item.get("status") == "indexed"}
        if any(current.get(key) != value for key, value in self.documents.items()):
            raise DocumentChanged("本轮依赖的文档已变更或删除，请重新提问。")

    def load_prompt(self, name: str) -> str:
        from app.services.chat_service import _load_prompt
        return _load_prompt(name)

    def emit(self, event: str, data: dict) -> None:
        if event == "sources":
            self.sources_emitted = True
        if event == "delta":
            self.delta_emitted = True
        if event in {"step_started", "step_done"}:
            self.steps.append({"event": event, **data})
        get_stream_writer()({"event": event, "data": data})


class ReservedStream:
    """Release even when HTTP disconnects before the generator's first next()."""

    def __init__(self, iterator, cancel, close):
        self.iterator = iterator
        self.cancel = cancel
        self.on_close = close
        self.closed = False

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return next(self.iterator)
        except BaseException:
            self.close()
            raise

    def close(self):
        if not self.closed:
            self.closed = True
            self.cancel()
            try:
                self.iterator.close()
            finally:
                self.on_close()


class KnowledgeQARuntime:
    def __init__(self, service):
        from app.agents.knowledge_qa.graph import build_graph

        self.service = service
        self.directory = json_store.data_dir / "agent"
        self.store = service.run_store()
        self.graph = build_graph(self.store.checkpointer)
        self.lock = service.coordinator.lock
        self.active = service.coordinator.active
        self.streams = service.coordinator.streams

    def open_stream(self, question: str, conversation: dict, top_k: int | None, filters: dict | None):
        conversation = deepcopy(conversation)
        conversation_id = conversation["id"]
        budget = RunBudget(seconds=settings.agent_max_seconds, max_llm_calls=settings.agent_max_llm_calls,
                           max_tool_calls=settings.agent_max_tool_calls)
        with self.lock:
            if conversation_id in self.active:
                raise HTTPException(status_code=409, detail={
                    "code": "conversation_busy", "message": "当前会话正在处理一个问题，请等待完成后重试。",
                })
            self.active[conversation_id] = budget

        def release():
            budget.cancelled.set()
            with self.lock:
                if self.active.get(conversation_id) is budget:
                    self.active.pop(conversation_id, None)
                    self.streams.pop(conversation_id, None)
        stream = ReservedStream(self._stream(question.strip(), conversation, top_k, filters or {}, budget), budget.cancelled.set, release)
        self.streams[conversation_id] = stream
        return stream

    def _stream(self, question: str, conversation: dict, top_k: int | None, filters: dict, budget: RunBudget):
        run_id = new_id("run")
        conversation_id = conversation["id"]
        graph_stream = None
        completed = False
        try:
            documents = [item for item in json_store.list_items("documents.json") if item.get("status") == "indexed"]
            scope = conversation.get("document_scope", {"mode": "all", "document_ids": []})
            if scope["mode"] == "selected":
                documents = [item for item in documents if item["id"] in scope["document_ids"]]
                if {item["id"] for item in documents} != set(scope["document_ids"]):
                    raise RuntimeError("所选文档已失效，请重新选择。")
            context = RunContext(
                service=self.service, conversation=conversation, budget=budget, top_k=top_k,
                filters={key: value for key, value in filters.items() if key != "document_ids"},
                documents={item["id"]: json.dumps(item, sort_keys=True, ensure_ascii=False) for item in documents},
            )
            context.check()
            self.store.record(run_id, conversation_id, "running", {"workflow_version": "knowledge-qa-v1"})
            history = self.service.list_messages(conversation_id)
            self.service._add_message(conversation_id, "user", question, [], scope_context=conversation, run_id=run_id)
            # History is loaded in the understand node; exclude this run's user message there.
            initial = {
                "run_id": run_id, "conversation_id": conversation_id, "workflow_version": "knowledge-qa-v1",
                "original_question": question, "resolved_question": question, "document_scope": scope,
                "scope_revision": conversation.get("scope_revision", 0), "allowed_document_ids": list(context.documents),
                "sources": [], "round": 0, "no_growth": 0, "executed_actions": [], "query_plan": {},
                "status": "running", "halted": False,
            }
            context.history = history
            yield {"event": "run_started", "data": {"run_id": run_id, "conversation_id": conversation_id}}
            final = None
            graph_stream = self.graph.stream(
                initial, {"configurable": {"thread_id": run_id}, "recursion_limit": 50},
                context=context, stream_mode=["custom", "updates"],
            )
            for kind, data in graph_stream:
                if kind == "custom":
                    yield data
                elif "finalize" in data:
                    final = data["finalize"]
            if final is None:
                raise RuntimeError("Agent 未返回完整结果。")
            # Read the final checkpoint only after graph execution (including writes) finishes.
            state = self.graph.get_state({"configurable": {"thread_id": run_id}}).values
            context.check(check_budget=False)
            self.store.record(run_id, conversation_id, state["status"], state["quality"]["agent"])
            sources = state.get("sources", [])
            if not context.sources_emitted:
                yield {"event": "sources", "data": {"conversation_id": conversation_id, "sources": sources}}
            if not context.delta_emitted:
                yield {"event": "delta", "data": {"text": state["final_answer"]}}
            completed = True
            yield {"event": "done", "data": {
                "conversation_id": conversation_id, "run_id": run_id, "status": state["status"],
                "answer": state["final_answer"], "sources": sources, "quality": state["quality"],
            }}
        except GeneratorExit:
            if not completed:
                self.store.record(run_id, conversation_id, "cancelled", {"reason": "stream_closed"})
            raise
        except Exception as exc:
            logger.exception("Knowledge QA run failed: %s", run_id)
            saved = any(item.get("run_id") == run_id and item["role"] == "assistant"
                        for item in self.service.list_messages(conversation_id))
            status = "needs_reconciliation" if saved else "cancelled" if isinstance(exc, RunCancelled) else "failed"
            self.store.record(run_id, conversation_id, status, {"reason": type(exc).__name__})
            message = str(exc) if isinstance(exc, (DocumentChanged, RunCancelled)) else "本轮处理已中断，请重试。"
            yield {"event": "error", "data": {"run_id": run_id, "message": message,
                                              "code": "document_changed" if isinstance(exc, DocumentChanged) else status}}
        finally:
            if graph_stream is not None:
                graph_stream.close()
            if json_store.get_item("conversations.json", conversation_id) is None:
                self.store.delete_conversation(conversation_id)

    def cancel_conversation(self, conversation_id: str) -> None:
        with self.lock:
            budget = self.active.get(conversation_id)
            if budget:
                budget.cancelled.set()
            else:
                self.store.delete_conversation(conversation_id)

    def close(self) -> None:
        for stream in list(self.streams.values()):
            stream.close()
