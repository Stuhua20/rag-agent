import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.chat import router
from app.services.answer_quality_service import answer_quality_service
from app.services.chat_service import ChatService
from app.services.knowledge_metadata_service import knowledge_metadata_service
from app.services.llm_service import llm_service
from app.services.query_understanding_service import query_understanding_service
from app.services.retrieval_service import retrieval_service


class ChatStreamingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ChatService()
        self.source = {
            "chunk_id": "test-chunk",
            "file_name": "sales.csv",
            "sheet_name": "销售",
            "content": "行 2：客户=甲公司；销售额=120000",
            "score_type": "exact_match",
        }
        self.plan = {"intent": "lookup", "sub_queries": ["甲公司销售额"]}
        self.retrieval = self.mock_method(
            self.service, "_prepare_retrieval",
            return_value=([self.source], None, {"full_scan_required": False}),
        )
        self.mock_method(self.service, "_get_or_create_conversation", return_value={"id": "test-conversation"})
        self.mock_method(self.service, "list_messages", return_value=[])
        self.saved = self.mock_method(self.service, "_add_message")
        self.mock_method(self.service, "_touch_conversation")
        self.mock_method(self.service, "_build_prompt", return_value="test prompt")
        self.mock_method(knowledge_metadata_service, "snapshot", return_value={})
        self.mock_method(query_understanding_service, "plan", return_value=self.plan)
        self.mock_method(retrieval_service, "score_threshold", return_value=0.2)
        self.model = self.mock_method(
            llm_service, "generate_answer_stream", return_value=iter(["甲公司销售额为", "120000元。"]),
        )

    def mock_method(self, target, name: str, **kwargs):
        patcher = patch.object(target, name, **kwargs)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def test_first_delta_arrives_before_model_finishes_or_verification_runs(self) -> None:
        generated = []

        def generate(prompt, system_prompt=None):
            generated.append("first")
            yield "甲公司销售额为"
            generated.append("second")
            yield "120000元。"
            generated.append("finished")

        self.model.side_effect = generate
        verifier = self.mock_method(answer_quality_service, "verify_answer", wraps=answer_quality_service.verify_answer)
        stream = self.service.ask_stream("甲公司销售额是多少？")
        self.addCleanup(stream.close)
        self.assertEqual(next(stream)["event"], "sources")
        self.assertEqual(generated, [])
        self.assertEqual(next(stream), {"event": "delta", "data": {"text": "甲公司销售额为"}})
        self.assertEqual(generated, ["first"])
        verifier.assert_not_called()
        self.assertEqual(next(stream)["data"]["text"], "120000元。")
        done = next(stream)
        self.assertEqual(done["event"], "done")
        self.assertEqual(done["data"]["answer"], "甲公司销售额为120000元。")
        self.assertEqual(generated, ["first", "second", "finished"])
        verifier.assert_called_once()
        self.assertEqual(list(stream), [])

    def test_failed_verification_replaces_draft_in_done_and_history(self) -> None:
        self.model.return_value = iter(["甲公司销售额为", "999元。"])
        events = list(self.service.ask_stream("甲公司销售额是多少？"))
        deltas = [event["data"]["text"] for event in events if event["event"] == "delta"]
        self.assertEqual(deltas, ["甲公司销售额为", "999元。"])
        done = events[-1]["data"]
        self.assertFalse(done["quality"]["answer_verifier"]["passed"])
        self.assertNotIn("999", done["answer"])
        self.assertIn("无法由当前引用证据核验", done["answer"])
        saved = self.saved.call_args.args
        self.assertEqual(saved[1:3], ("assistant", done["answer"]))
        self.assertEqual(saved[4], done["quality"])

    def test_internal_references_are_removed_from_final_answer(self) -> None:
        self.model.return_value = iter(["甲公司销售额为120000元。", "[来源1]"])
        done = list(self.service.ask_stream("甲公司销售额是多少？"))[-1]["data"]
        self.assertEqual(done["answer"], "甲公司销售额为120000元。")
        self.assertTrue(done["quality"]["answer_verifier"]["sanitized"])

    def test_missing_evidence_returns_fallback_without_calling_model(self) -> None:
        self.retrieval.return_value = ([], None, {"full_scan_required": False})
        events = list(self.service.ask_stream("甲公司销售额是多少？"))
        self.assertEqual([event["event"] for event in events], ["sources", "delta", "done"])
        self.assertEqual(events[1]["data"]["text"], events[2]["data"]["answer"])
        self.assertFalse(events[2]["data"]["quality"]["evidence_gate"]["passed"])
        self.model.assert_not_called()

    def test_deterministic_answer_is_sent_once_without_model(self) -> None:
        answer = "甲公司销售额为120000元。"
        self.retrieval.return_value = ([self.source], answer, {"deterministic": True})
        events = list(self.service.ask_stream("甲公司销售额是多少？"))
        self.assertEqual([event["event"] for event in events], ["sources", "delta", "done"])
        self.assertEqual(events[1]["data"]["text"], answer)
        self.assertEqual(events[2]["data"]["answer"], answer)
        self.model.assert_not_called()

    def test_empty_model_stream_returns_verified_fallback(self) -> None:
        self.model.return_value = iter([""])
        events = list(self.service.ask_stream("甲公司销售额是多少？"))
        self.assertEqual([event["event"] for event in events], ["sources", "delta", "done"])
        self.assertIn("未生成有效回答", events[-1]["data"]["answer"])
        self.assertEqual(events[1]["data"]["text"], events[-1]["data"]["answer"])

    def test_clarification_does_not_start_retrieval_or_model(self) -> None:
        self.plan.update(needs_clarification=True, clarification_question="请问是哪家公司？")
        events = list(self.service.ask_stream("那家公司的销售额呢？"))
        self.assertEqual(events[-1]["data"]["answer"], "请问是哪家公司？")
        self.retrieval.assert_not_called()
        self.model.assert_not_called()

    def test_model_failure_preserves_prior_delta_and_emits_error_without_done(self) -> None:
        def generate(prompt, system_prompt=None):
            yield "甲公司销售额为"
            raise RuntimeError("test stream interrupted")

        self.model.side_effect = generate
        app = FastAPI()
        app.include_router(router)
        with patch("app.routers.chat.chat_service", self.service), TestClient(app) as client:
            response = client.post("/api/chat/stream", json={"question": "甲公司销售额是多少？"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])
        self.assertEqual(response.headers["x-accel-buffering"], "no")
        self.assertIn("event: delta\n", response.text)
        self.assertIn("event: error\n", response.text)
        self.assertIn("test stream interrupted", response.text)
        self.assertNotIn("event: done\n", response.text)
        self.assertEqual(self.saved.call_count, 1)


if __name__ == "__main__":
    unittest.main()
