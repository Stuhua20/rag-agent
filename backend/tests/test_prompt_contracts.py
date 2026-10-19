import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import prompts as prompt_routes
from app.services import chat_service as chat_module
from app.services import query_understanding_service as query_module
from app.services.chat_service import ChatService
from app.services.knowledge_metadata_service import knowledge_metadata_service
from app.services.llm_service import llm_service
from app.services.query_understanding_service import QueryUnderstandingService, query_understanding_service


class PromptEditingTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="prompt-contracts-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for name in prompt_routes.MANAGED_PROMPTS:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text((prompt_routes.PROMPTS_DIR / name).read_text(encoding="utf-8"), encoding="utf-8")
        for module in (prompt_routes, chat_module, query_module):
            patcher = patch.object(module, "PROMPTS_DIR", root)
            patcher.start()
            self.addCleanup(patcher.stop)
        prompt_routes._clear_prompt_caches()
        self.addCleanup(prompt_routes._clear_prompt_caches)
        self.root = root
        app = FastAPI()
        app.include_router(prompt_routes.router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_deleting_any_required_answer_variable_is_rejected_without_writing(self) -> None:
        path = self.root / "rag/answer.md"
        original = path.read_text(encoding="utf-8")
        for variable in prompt_routes.REQUIRED_PLACEHOLDERS["rag/answer.md"]:
            with self.subTest(variable=variable):
                response = self.client.put("/api/prompts/rag/answer.md", json={
                    "content": original.replace(variable, ""),
                })
                self.assertEqual(response.status_code, 400)
                self.assertIn(variable, response.json()["detail"])
                self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_online_save_invalidates_both_runtime_caches(self) -> None:
        name = "query/planner.md"
        original = chat_module._load_prompt(name)
        self.assertEqual(query_module._load_prompt(name), original)
        updated = original + "\n\n新增通用约束。"
        response = self.client.put("/api/prompts/" + name, json={"content": updated})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(chat_module._load_prompt(name), updated)
        self.assertEqual(query_module._load_prompt(name), updated)


class QueryContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = QueryUnderstandingService()

    def test_model_cannot_override_explicit_sheet_filter(self) -> None:
        self.assertEqual(self.service._normalize_filters(
            {"sheet_name": "other"}, {"sheet_names": ["selected", "other"]}, {"sheet_name": "selected"},
        ), {"sheet_name": "selected"})

    def test_model_sheet_requires_available_metadata(self) -> None:
        for metadata in ({}, {"sheet_names": []}, {"sheet_names": ["available"]}):
            with self.subTest(metadata=metadata):
                self.assertEqual(self.service._normalize_filters({"sheet_name": "invented"}, metadata, None), {})
        self.assertEqual(self.service._normalize_filters(
            {"sheet_name": "available"}, {"sheet_names": ["available"]}, None,
        ), {"sheet_name": "available"})

    def test_identifier_only_translations_can_remain_unchanged(self) -> None:
        queries = ["XYZ", "id-42", "10.1234/example"]
        with patch.object(llm_service, "generate_answer", return_value=json.dumps(queries)):
            self.assertEqual(self.service._translate_queries(queries, "Chinese"), queries)

    def test_wrong_language_or_changed_identifier_is_rejected(self) -> None:
        cases = [
            (["describe the method"], ["describe the method"]),
            (["XYZ"], ["ABC"]),
            (["id-42"], ["id-43"]),
        ]
        for queries, translations in cases:
            with self.subTest(queries=queries), patch.object(
                llm_service, "generate_answer", return_value=json.dumps(translations),
            ):
                self.assertEqual(self.service._translate_queries(queries, "Chinese"), [])

    def test_translation_alignment_and_mixed_identifier_batch(self) -> None:
        with patch.object(llm_service, "generate_answer", return_value='["XYZ", "操作说明"]'):
            self.assertEqual(
                self.service._translate_queries(["XYZ", "instructions"], "Chinese"), ["XYZ", "操作说明"],
            )
        with patch.object(llm_service, "generate_answer", return_value='["操作说明"]'):
            self.assertEqual(self.service._translate_queries(["XYZ", "instructions"], "Chinese"), [])


class AnswerPromptIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ChatService()
        self.source = {"content": "已记录的操作说明。", "score_type": "exact_match"}
        self.state = {"full_scan_required": True, "full_scan_complete": True}
        mocks = [
            (self.service, "_get_or_create_conversation", {"id": "prompt-test"}),
            (self.service, "list_messages", []),
            (self.service, "_add_message", None),
            (self.service, "_touch_conversation", None),
            (self.service, "_prepare_retrieval", ([self.source], self.state)),
            (knowledge_metadata_service, "snapshot", {}),
            (query_understanding_service, "plan", {
                "intent": "lookup", "resolved_question": "补全后的操作问题", "retrieval": {"need_full_scan": False},
            }),
        ]
        for target, name, result in mocks:
            patcher = patch.object(target, name, return_value=result)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_sync_and_stream_receive_actual_evidence_state_separate_from_plan(self) -> None:
        for stream in (False, True):
            with self.subTest(stream=stream), patch.object(
                llm_service, "generate_answer", return_value="已记录的操作说明。",
            ) as sync_model, patch.object(
                llm_service, "generate_answer_stream", return_value=iter(["已记录的操作说明。"]),
            ) as stream_model:
                result = list(self.service.ask_stream("如何操作？"))[-1]["data"] if stream else self.service.ask("如何操作？")
                model = stream_model if stream else sync_model
                prompt = model.call_args.args[0]
                report = json.loads(prompt.split("【证据检查结果】\n", 1)[1].split("\n\n【已检索知识库资料】", 1)[0])
                self.assertTrue(report["full_scan_complete"])
                self.assertEqual(report, result["quality"]["evidence_gate"])
                self.assertIn('"need_full_scan": false', prompt)
                self.assertIn("【补全后的问题】\n补全后的操作问题", prompt)
                self.assertTrue(prompt.endswith("【用户问题】\n如何操作？"))
                self.assertIn("system_prompt", model.call_args.kwargs)

    def test_missing_report_does_not_claim_complete_coverage(self) -> None:
        prompt = self.service._build_prompt("问题", [self.source])
        self.assertIn("【证据检查结果】\n{}", prompt)


if __name__ == "__main__":
    unittest.main()
