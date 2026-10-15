import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.routers.chat import router
from app.services.answer_quality_service import answer_quality_service
from app.services.chat_service import ChatService, chat_service
from app.services.json_store_service import json_store
from app.services.llm_service import llm_service
from app.services.query_understanding_service import QueryUnderstandingService, query_understanding_service
from app.services.retrieval_service import retrieval_service


class QueryResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = QueryUnderstandingService()
        translator = patch.object(self.service, "_translate_queries", return_value=[])
        self.translate = translator.start()
        self.addCleanup(translator.stop)

    def plan(self, question: str, raw: dict, history: str = "无") -> dict:
        with patch.object(llm_service, "generate_answer", return_value=json.dumps(raw, ensure_ascii=False)):
            return self.service.plan(question, history)

    def test_followup_keeps_original_and_adds_resolved_and_bilingual_queries(self) -> None:
        original = "那2月份呢？"
        resolved = "A经销商2月份的销售额合计是多少？"
        plan = self.plan(original, {
            "resolved_question": resolved,
            "retrieval_queries": ["What is distributor A's total sales in February?"],
        }, "用户：A经销商1月份的销售额合计是多少？")
        self.assertEqual(plan["original_question"], original)
        self.assertEqual(plan["resolved_question"], resolved)
        self.assertEqual(plan["retrieval_queries"][:2], [original, resolved])
        self.assertIn("What is distributor A's total sales in February?", plan["retrieval_queries"])
        self.assertEqual(plan["intent"], "summary")
        self.assertFalse(plan["needs_clarification"])

    def test_reference_without_history_cannot_accept_invented_resolution(self) -> None:
        plan = self.plan("那2月份呢？", {"resolved_question": "A经销商2月份销售额是多少？"})
        self.assertTrue(plan["needs_clarification"])
        self.assertEqual(plan["resolved_question"], "那2月份呢？")
        self.assertEqual(plan["retrieval_queries"], ["那2月份呢？"])
        self.assertTrue(plan["clarification_question"])
        self.translate.assert_not_called()

    def test_planner_can_request_specific_clarification_for_ambiguous_history(self) -> None:
        plan = self.plan("它的销售额呢？", {
            "needs_clarification": True,
            "clarification_question": "你指的是A经销商还是B经销商？",
            "resolved_question": "A经销商销售额是多少？",
        }, "用户：比较A经销商和B经销商。")
        self.assertTrue(plan["needs_clarification"])
        self.assertEqual(plan["resolved_question"], "它的销售额呢？")
        self.assertEqual(plan["clarification_question"], "你指的是A经销商还是B经销商？")

    def test_failed_or_invalid_planner_clarifies_context_dependent_requests(self) -> None:
        for response in (RuntimeError("offline"), "not json", "{}"):
            for question in ("那2月份呢？", "2月份呢？", "What about February?"):
                with self.subTest(response=str(response), question=question):
                    kwargs = {"side_effect": response} if isinstance(response, Exception) else {"return_value": response}
                    with patch.object(llm_service, "generate_answer", **kwargs):
                        plan = self.service.plan(question, "用户：A经销商1月销售额是多少？")
                    self.assertTrue(plan["needs_clarification"])
                    self.assertEqual(plan["resolved_question"], question)

    def test_standalone_and_legacy_plans_keep_original_question(self) -> None:
        original = "A经销商销售额是多少？"
        for raw in ({}, {"sub_queries": [original]}, {"resolved_question": {"bad": "value"}}):
            with self.subTest(raw=raw):
                plan = self.plan(original, raw)
                self.assertEqual(plan["resolved_question"], original)
                self.assertFalse(plan["needs_clarification"])

    def test_standalone_question_falls_back_when_planner_is_unavailable(self) -> None:
        with patch.object(llm_service, "generate_answer", side_effect=RuntimeError("offline")):
            plan = self.service.plan("A经销商销售额合计是多少？")
        self.assertFalse(plan["needs_clarification"])
        self.assertEqual(plan["intent"], "summary")
        self.assertEqual(plan["resolved_question"], plan["original_question"])

    def test_unchanged_or_malformed_resolution_does_not_resolve_a_reference(self) -> None:
        for value in (None, "", [], "那2月份呢？", "它2月份的销售额是多少？", "x" * 2001):
            with self.subTest(value=str(value)[:30]):
                plan = self.plan("那2月份呢？", {"resolved_question": value}, "用户：A经销商1月销售额是多少？")
                self.assertTrue(plan["needs_clarification"])


class ResolvedQuestionChatTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="resolved-question-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for target, name, value in (
            (json_store, "data_dir", root / "data"),
            (settings, "storage_dir", root / "storage"),
        ):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        json_store.initialize()
        config = json_store.read_json("settings.json")
        config["llm"]["mock"] = True
        config["embedding"]["mock"] = True
        json_store.write_json("settings.json", config)
        translator = patch.object(query_understanding_service, "_translate_queries", return_value=[])
        translator.start()
        self.addCleanup(translator.stop)
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def seed_conversation(self, message: str = "A经销商1月份的销售额合计是多少？") -> str:
        conversation = chat_service.create_conversation("销售查询")
        chat_service._add_message(conversation["id"], "user", message, [])
        chat_service._add_message(conversation["id"], "assistant", "上轮回答只用于理解上下文。", [])
        return conversation["id"]

    def seed_table(self) -> None:
        json_store.write_json("documents.json", [{"id": "doc", "file_name": "sales.csv", "status": "indexed"}])
        json_store.write_json("chunks.json", [{
            "id": "chunk", "document_id": "doc", "sheet_id": "sheet", "sheet_name": "sales",
            "row_start": 2, "row_end": 5, "columns": ["客户", "月份", "销售额"],
            "content": (
                "行 2：客户=A经销商；月份=1月份；销售额=10\n"
                "行 3：客户=A经销商；月份=2月份；销售额=20\n"
                "行 4：客户=A经销商；月份=2月份；销售额=30\n"
                "行 5：客户=B经销商；月份=2月份；销售额=900"
            ),
            "metadata": {},
        }])

    def send(self, path: str, question: str, conversation_id: str | None = None) -> dict:
        response = self.client.post(path, json={"question": question, "conversation_id": conversation_id})
        self.assertEqual(response.status_code, 200, response.text)
        if path.endswith("/stream"):
            names = [line[7:] for line in response.text.splitlines() if line.startswith("event: ")]
            self.assertEqual(names, ["sources", "delta", "done"])
            data = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
            return {"sources": data[0]["sources"], **data[-1]}
        return response.json()

    def test_sync_and_stream_compute_resolved_scope_and_keep_history_original(self) -> None:
        self.seed_table()
        original = "那2月份呢？"
        resolved = "A经销商2月份的销售额合计是多少？"
        raw = {"resolved_question": resolved, "intent": "summary"}
        for path in ("/api/chat", "/api/chat/stream"):
            with self.subTest(path=path):
                conversation_id = self.seed_conversation()
                with (
                    patch.object(llm_service, "generate_answer", return_value=json.dumps(raw)) as planner,
                    patch.object(llm_service, "generate_answer_stream") as answer_stream,
                    patch.object(answer_quality_service, "evaluate_evidence", wraps=answer_quality_service.evaluate_evidence) as gate,
                    patch.object(answer_quality_service, "verify_answer", wraps=answer_quality_service.verify_answer) as verifier,
                ):
                    result = self.send(path, original, conversation_id)
                self.assertIn("合计为 50", result["answer"])
                self.assertTrue(result["quality"]["evidence_gate"]["deterministic"])
                self.assertEqual(gate.call_args.args[0], resolved)
                self.assertEqual(verifier.call_args.args[1], resolved)
                planner.assert_called_once()
                answer_stream.assert_not_called()
                history = chat_service.list_messages(conversation_id)
                self.assertEqual(history[-2]["content"], original)
                self.assertEqual(history[-1]["quality"], result["quality"])
                trace = result["quality"]["query_understanding"]
                self.assertEqual(trace["original_question"], original)
                self.assertEqual(trace["resolved_question"], resolved)

    def test_clarification_skips_retrieval_and_answer_generation_on_both_endpoints(self) -> None:
        cases = (
            (None, {"resolved_question": "A经销商2月销售额是多少？"}),
            ("用户：比较A经销商和B经销商。", {
                "needs_clarification": True, "clarification_question": "请确认是哪家经销商？",
            }),
        )
        for path in ("/api/chat", "/api/chat/stream"):
            for history, raw in cases:
                with self.subTest(path=path, history=history):
                    conversation_id = self.seed_conversation(history) if history else None
                    with (
                        patch.object(llm_service, "generate_answer", return_value=json.dumps(raw)) as planner,
                        patch.object(llm_service, "generate_answer_stream") as answer_stream,
                        patch.object(chat_service, "_prepare_retrieval") as retrieve,
                    ):
                        result = self.send(path, "那2月份呢？", conversation_id)
                    self.assertTrue(result["quality"]["query_understanding"]["needs_clarification"])
                    self.assertTrue(result["answer"])
                    self.assertEqual(result["sources"], [])
                    retrieve.assert_not_called()
                    answer_stream.assert_not_called()
                    planner.assert_called_once()
                    self.assertEqual(chat_service.list_messages(result["conversation_id"])[-2]["content"], "那2月份呢？")

    def test_resolved_question_is_sent_to_search_and_prompt_but_is_not_evidence(self) -> None:
        original = "那2月份呢？"
        resolved = "A经销商2月份销售额是多少？"
        source = {
            "chunk_id": "chunk", "document_id": "doc", "sheet_id": "sheet", "file_name": "sales.csv",
            "sheet_name": "sales", "row_start": 2, "row_end": 2, "score": 1.0,
            "content": "行 2：客户=A经销商；月份=2月份；销售额=20",
        }
        raw = {"resolved_question": resolved}
        for path in ("/api/chat", "/api/chat/stream"):
            with self.subTest(path=path):
                conversation_id = self.seed_conversation()
                self.assertEqual(chat_service.list_messages(conversation_id)[-1]["sources"], [])
                with (
                    patch.object(llm_service, "generate_answer", side_effect=[json.dumps(raw), "销售额为20。"]),
                    patch.object(llm_service, "generate_answer_stream", return_value=iter(["销售额为20。"])) as stream,
                    patch.object(retrieval_service, "search_multiple", return_value=[source]) as search,
                ):
                    result = self.send(path, original, conversation_id)
                self.assertIn(resolved, search.call_args.args[0])
                self.assertEqual(result["answer"], "销售额为20。")
                prompt = chat_service._build_prompt(original, [source], raw, "用户：上一轮问题")
                self.assertIn("【补全后的问题】\n" + resolved, prompt)
                self.assertTrue(prompt.endswith("【用户问题】\n" + original))
                if path.endswith("/stream"):
                    self.assertIn("【补全后的问题】\n" + resolved, stream.call_args.args[0])

    def test_history_and_resolution_cannot_replace_missing_knowledge_evidence(self) -> None:
        for path in ("/api/chat", "/api/chat/stream"):
            with self.subTest(path=path):
                conversation_id = self.seed_conversation("A经销商1月份的销售额是999，请比较2月份。")
                with patch.object(llm_service, "generate_answer", return_value=json.dumps({
                    "resolved_question": "A经销商2月份销售额是多少？",
                })) as planner:
                    result = self.send(path, "那2月份呢？", conversation_id)
                self.assertEqual(result["sources"], [])
                self.assertEqual(result["answer"], "知识库中未找到明确依据。")
                self.assertFalse(result["quality"]["evidence_gate"]["passed"])
                planner.assert_called_once()

    def test_numbers_introduced_by_resolution_are_not_accepted_as_user_supplied_facts(self) -> None:
        source = {
            "chunk_id": "chunk", "file_name": "sales.csv", "sheet_name": "sales",
            "score_type": "exact_match", "content": "行 2：客户=A经销商；销售额=20",
        }
        for path in ("/api/chat", "/api/chat/stream"):
            with self.subTest(path=path):
                conversation_id = self.seed_conversation()
                with (
                    patch.object(llm_service, "generate_answer", side_effect=[json.dumps({
                        "resolved_question": "A经销商999的销售额是多少？",
                    }), "销售额为999。"]),
                    patch.object(llm_service, "generate_answer_stream", return_value=iter(["销售额为999。"])),
                    patch.object(retrieval_service, "search_multiple", return_value=[source]),
                ):
                    result = self.send(path, "那2月份呢？", conversation_id)
                self.assertFalse(result["quality"]["answer_verifier"]["passed"])
                self.assertNotIn("999", result["answer"])
                self.assertEqual(chat_service.list_messages(conversation_id)[-1]["content"], result["answer"])

    def test_legacy_plan_without_new_fields_still_works(self) -> None:
        self.seed_table()
        question = "销售额合计是多少？"
        with patch.object(query_understanding_service, "plan", return_value={"intent": "summary"}):
            result = ChatService().ask(question)
        self.assertIn("合计为 960", result["answer"])
        self.assertEqual(result["quality"]["query_understanding"]["resolved_question"], question)


if __name__ == "__main__":
    unittest.main()
