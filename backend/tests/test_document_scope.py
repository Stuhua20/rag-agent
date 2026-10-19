import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.config import settings
from app.routers.chat import router as chat_router
from app.routers.conversations import router as conversations_router
from app.services.chat_service import chat_service
from app.services.conversation_context_service import conversation_context_service
from app.services.json_store_service import json_store
from app.services.knowledge_metadata_service import knowledge_metadata_service
from app.services.llm_service import llm_service
from app.services.query_understanding_service import query_understanding_service
from app.services.retrieval_service import retrieval_service


class DocumentScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="document-scope-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for target, name, value in ((json_store, "data_dir", root / "data"), (settings, "storage_dir", root / "storage")):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        json_store.initialize()
        config = json_store.read_json("settings.json")
        config["retrieval"].update(search_mode="keyword", score_threshold=0.1)
        json_store.write_json("settings.json", config)
        for doc_id, amount in (("a", 100), ("b", 900)):
            metadata = {"file_name": "同名销售.csv", "sheet_name": "销售"}
            json_store.add_item("documents.json", {
                "id": doc_id, "file_name": "同名销售.csv", "status": "indexed", "file_type": "csv",
            })
            json_store.add_item("sheets.json", {
                "id": "sheet-" + doc_id, "document_id": doc_id, "sheet_name": "销售",
                "headers": ["客户", "销售额", "仅" + doc_id + "字段"],
            })
            json_store.add_item("chunks.json", {
                "id": "chunk-" + doc_id, "document_id": doc_id, "sheet_id": "sheet-" + doc_id,
                "sheet_name": "销售", "columns": ["客户", "销售额"], "metadata": metadata,
                "content": f"行 2：客户=甲公司；销售额={amount}", "row_start": 2, "row_end": 2,
            })
            json_store.add_item("embeddings.json", {
                "id": "embedding-" + doc_id, "document_id": doc_id, "chunk_id": "chunk-" + doc_id,
                "vector": [], "metadata": metadata,
            })
        app = FastAPI()
        app.include_router(chat_router)
        app.include_router(conversations_router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    @staticmethod
    def selected(*ids: str) -> dict:
        return {"mode": "selected", "document_ids": list(ids)}

    def create(self, *ids: str) -> dict:
        response = self.client.post("/api/conversations", json={"document_scope": self.selected(*ids)})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    @staticmethod
    def events(response) -> list[dict]:
        return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]

    def test_scope_persists_by_conversation_with_same_named_documents(self) -> None:
        a, b = self.create("a"), self.create("b")
        for conversation, doc_id in ((a, "a"), (b, "b")):
            self.assertEqual(self.client.get(f"/api/conversations/{conversation['id']}").json()["document_scope"], self.selected(doc_id))

    def test_empty_and_invalid_selections_do_not_create_conversation(self) -> None:
        for scope, status in ((self.selected(), 422), (self.selected("missing"), 409), ({"mode": "all", "document_ids": ["a"]}, 422)):
            self.assertEqual(self.client.post("/api/conversations", json={"document_scope": scope}).status_code, status)
        self.assertEqual(json_store.list_items("conversations.json"), [])

    def test_legacy_defaults_without_migration_and_can_be_updated(self) -> None:
        original = {"id": "legacy", "title": "旧会话"}
        json_store.add_item("conversations.json", original)
        detail = self.client.get("/api/conversations/legacy").json()
        self.assertEqual(detail["document_scope"], {"mode": "all", "document_ids": []})
        self.assertEqual(detail["scope_revision"], 0)
        self.assertEqual(json_store.get_item("conversations.json", "legacy"), original)
        response = self.client.patch("/api/conversations/legacy", json={"document_scope": self.selected("a"), "expected_scope_revision": 0})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["scope_revision"], 1)

    def test_same_set_keeps_revision_and_stale_changes_are_rejected(self) -> None:
        conversation = self.create("a", "b")
        url = f"/api/conversations/{conversation['id']}"
        response = self.client.patch(url, json={"document_scope": self.selected("b", "a", "a"), "expected_scope_revision": 0})
        self.assertEqual(response.json()["scope_revision"], 0)
        response = self.client.patch(url, json={"document_scope": self.selected("a"), "expected_scope_revision": 0})
        self.assertEqual(response.json()["scope_revision"], 1)
        response = self.client.patch(url, json={"document_scope": self.selected("b"), "expected_scope_revision": 0})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get(url).json()["document_scope"], self.selected("a"))

    def test_concurrent_scope_updates_have_one_winner(self) -> None:
        conversation = self.create("a")
        def update(scope):
            try:
                return chat_service.update_document_scope(conversation["id"], scope, 0)["scope_revision"]
            except HTTPException as exc:
                return exc.status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(update, [self.selected("b"), {"mode": "all", "document_ids": []}]))
        self.assertCountEqual(results, [1, 409])

    def test_retrieval_metadata_and_citations_obey_scope_even_when_empty(self) -> None:
        for ids in (["a"], ["b"], []):
            with self.subTest(ids=ids):
                sources = retrieval_service.search_multiple(["销售额", "甲公司"], filters={"document_ids": ids}, full_scan=True)
                ranked = retrieval_service.search_multiple(["销售额", "甲公司"], filters={"document_ids": ids}, top_k=1)
                self.assertEqual({item["document_id"] for item in ranked}, set(ids))
                citations = retrieval_service.sources_for_chunk_ids(["chunk-a", "chunk-b"], document_ids=ids)
                for result in (sources, citations):
                    self.assertEqual({item["document_id"] for item in result}, set(ids))
        metadata = knowledge_metadata_service.snapshot(document_ids=["a"])
        self.assertIn("仅a字段", metadata["headers"])
        self.assertNotIn("仅b字段", metadata["headers"])
        self.assertEqual(knowledge_metadata_service.snapshot(document_ids=[])["file_names"], [])

    def test_model_plan_cannot_override_scope_for_retrieval(self) -> None:
        plan = {"intent": "lookup", "sub_queries": ["销售额"], "filters": {"document_ids": ["b"]}}
        sources, state = chat_service._prepare_retrieval("甲公司销售额是多少？", plan, None, {"document_ids": ["a"]})
        self.assertEqual({item["document_id"] for item in sources}, {"a"})
        self.assertTrue(all("900" not in item["content"] for item in sources))

    def test_both_chat_endpoints_retrieve_and_save_only_selected_documents(self) -> None:
        for endpoint in ("/api/chat", "/api/chat/stream"):
            for ids in (("a",), ("b",), ("a", "b")):
                with self.subTest(endpoint=endpoint, ids=ids):
                    conversation = self.create(*ids)
                    facts = {"a": "甲公司销售额为100元。", "b": "甲公司销售额为900元。"}
                    answer = "\n".join(facts[item] for item in ids)
                    with patch.object(query_understanding_service, "plan", return_value={"intent": "lookup", "sub_queries": ["销售额"]}), patch.object(llm_service, "generate_answer", return_value=answer) as model, patch.object(llm_service, "generate_answer_stream", return_value=iter([answer])) as stream:
                        response = self.client.post(endpoint, json={"conversation_id": conversation["id"], "question": "所选文档中记载的销售额是多少？"})
                    self.assertEqual(response.status_code, 200, response.text)
                    result = self.events(response)[-1] if endpoint.endswith("stream") else response.json()
                    self.assertEqual(answer, result["answer"])
                    messages = chat_service.list_messages(conversation["id"])
                    self.assertEqual({item["document_id"] for item in messages[-1]["sources"]}, set(ids))
                    self.assertTrue(all(item["document_scope"] == self.selected(*ids) for item in messages))
                    (stream if endpoint.endswith("stream") else model).assert_called_once()

    def test_streaming_model_and_planner_receive_only_selected_evidence(self) -> None:
        conversation = self.create("a")
        with patch.object(query_understanding_service, "plan", return_value={"intent": "lookup", "sub_queries": ["销售额"], "filters": {"document_ids": ["b"]}}) as planner, patch.object(llm_service, "generate_answer_stream", return_value=iter(["甲公司销售额", "为100元。"])) as model:
            response = self.client.post("/api/chat/stream", json={"conversation_id": conversation["id"], "question": "甲公司销售额是多少？"})
        events = self.events(response)
        self.assertEqual([item["text"] for item in events if "text" in item], ["甲公司销售额", "为100元。"])
        self.assertEqual({item["document_id"] for item in events[0]["sources"]}, {"a"})
        self.assertNotIn("仅b字段", str(planner.call_args.args[2]))
        self.assertNotIn("销售额=900", model.call_args.args[0])
        self.assertEqual(events[-1]["answer"], "甲公司销售额为100元。")

    def test_no_match_never_expands_to_all_documents(self) -> None:
        conversation = self.create("a")
        chunk = json_store.get_item("chunks.json", "chunk-b")
        json_store.update_item("chunks.json", "chunk-b", {"content": chunk["content"] + "；备注=southonlyterm"})
        self.assertEqual(retrieval_service.search("southonlyterm")[0]["document_id"], "b")
        with patch.object(query_understanding_service, "plan", return_value={"intent": "lookup", "sub_queries": ["southonlyterm"]}), patch.object(llm_service, "generate_answer_stream") as model:
            response = self.client.post("/api/chat/stream", json={"conversation_id": conversation["id"], "question": "southonlyterm"})
        events = self.events(response)
        self.assertEqual(events[0]["sources"], [])
        self.assertEqual(events[-1]["answer"], "所选文档中未找到明确依据。")
        model.assert_not_called()

    def test_deleted_unindexed_and_stale_scope_fail_before_sse_or_history(self) -> None:
        conversation = self.create("a")
        for status in ("failed", None):
            if status is None:
                json_store.delete_item("documents.json", "a")
            else:
                json_store.update_item("documents.json", "a", {"status": status})
            for endpoint in ("/api/chat", "/api/chat/stream"):
                response = self.client.post(endpoint, json={"conversation_id": conversation["id"], "question": "销售额？"})
                self.assertEqual(response.status_code, 409)
                self.assertIn("application/json", response.headers["content-type"])
            self.assertEqual(self.client.get(f"/api/conversations/{conversation['id']}").json()["invalid_document_ids"], ["a"])
        self.assertEqual(chat_service.list_messages(conversation["id"]), [])
        chat_service.update_document_scope(conversation["id"], self.selected("b"), 0)
        for endpoint in ("/api/chat", "/api/chat/stream"):
            response = self.client.post(endpoint, json={"conversation_id": conversation["id"], "question": "销售额？", "expected_scope_revision": 0})
            self.assertEqual(response.status_code, 409)
        self.assertEqual(chat_service.list_messages(conversation["id"]), [])

    def test_scope_switch_keeps_history_but_resets_model_context(self) -> None:
        conversation = self.create("a")
        chat_service._add_message(conversation["id"], "user", "旧范围秘密标记", [], scope_context=conversation)
        chat_service.update_document_scope(conversation["id"], self.selected("b"), 0)
        with patch.object(query_understanding_service, "plan", return_value={"intent": "lookup", "sub_queries": ["销售额"]}) as planner, patch.object(llm_service, "generate_answer", return_value="甲公司销售额为900元。") as model:
            chat_service.ask("甲公司销售额是多少？", conversation["id"], expected_scope_revision=1)
        self.assertEqual(planner.call_args.args[1], "无")
        self.assertNotIn("旧范围秘密标记", model.call_args.args[0])
        messages = chat_service.list_messages(conversation["id"])
        self.assertEqual(len(messages), 3)
        self.assertIn("900", conversation_context_service.build_context(messages, scope_revision=1))
        self.assertNotIn("旧范围秘密标记", conversation_context_service.build_context(messages, scope_revision=1))
        chat_service.update_document_scope(conversation["id"], self.selected("a"), 1)
        self.assertEqual(conversation_context_service.build_context(messages, scope_revision=2), "无")

    def test_in_flight_run_keeps_original_scope_after_another_tab_changes_it(self) -> None:
        conversation = self.create("a")
        with patch.object(query_understanding_service, "plan", return_value={"intent": "lookup", "sub_queries": ["销售额"]}), patch.object(llm_service, "generate_answer_stream", return_value=iter(["甲公司销售额为100元。"])):
            stream = chat_service.ask_stream("甲公司销售额是多少？", conversation["id"])
            self.assertEqual({item["document_id"] for item in next(stream)["data"]["sources"]}, {"a"})
            chat_service.update_document_scope(conversation["id"], self.selected("b"), 0)
            list(stream)
        saved = chat_service.list_messages(conversation["id"])[-1]
        self.assertEqual(saved["scope_revision"], 0)
        self.assertEqual(saved["document_scope"], self.selected("a"))
        self.assertEqual(chat_service.get_conversation(conversation["id"])["document_scope"], self.selected("b"))


if __name__ == "__main__":
    unittest.main()
