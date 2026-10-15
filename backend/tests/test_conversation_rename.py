import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.routers.conversations import router
from app.services.chat_service import chat_service
from app.services.json_store_service import json_store


class ConversationRenameTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="conversation-rename-")
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
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.conversation = self.client.post("/api/conversations", json={"title": "原名称"}).json()
        self.url = f"/api/conversations/{self.conversation['id']}/title"

    def test_rename_trims_and_persists_without_changing_other_fields(self) -> None:
        chat_service._add_message(self.conversation["id"], "user", "历史问题", [])
        messages = json_store.read_json("messages.json")
        response = self.client.patch(self.url, json={"title": "  销售分析 🐈  "})
        self.assertEqual(response.status_code, 200)
        expected = {**self.conversation, "title": "销售分析 🐈"}
        self.assertEqual(response.json(), expected)
        self.assertEqual(json_store.get_item("conversations.json", self.conversation["id"]), expected)
        self.assertEqual(self.client.get("/api/conversations").json(), [expected])
        self.assertEqual(json_store.read_json("messages.json"), messages)

    def test_invalid_names_are_rejected_without_writing(self) -> None:
        for title in ("", " \n\t\u3000", "中" * 101, "🐈" * 101, None, 123, [], {}):
            with self.subTest(title=title):
                self.assertEqual(self.client.patch(self.url, json={"title": title}).status_code, 422)
                self.assertEqual(json_store.get_item("conversations.json", self.conversation["id"]), self.conversation)
        self.assertEqual(self.client.patch(self.url, json={}).status_code, 422)

    def test_unicode_limit_is_applied_after_trimming(self) -> None:
        for title in ("中" * 100, "🐈" * 100):
            response = self.client.patch(self.url, json={"title": "  " + title + "  "})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["title"], title)

    def test_missing_and_deleted_conversations_return_404(self) -> None:
        self.assertEqual(self.client.patch("/api/conversations/missing/title", json={"title": "名称"}).status_code, 404)
        self.client.delete(f"/api/conversations/{self.conversation['id']}")
        self.assertEqual(self.client.patch(self.url, json={"title": "名称"}).status_code, 404)
        self.assertEqual(json_store.list_items("conversations.json"), [])

    def test_duplicate_names_and_same_name_are_allowed_without_reordering(self) -> None:
        other = self.client.post("/api/conversations", json={"title": "重复名称"}).json()
        before_ids = [item["id"] for item in self.client.get("/api/conversations").json()]
        for _ in range(2):
            response = self.client.patch(self.url, json={"title": other["title"]})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["updated_at"], self.conversation["updated_at"])
        self.assertEqual([item["id"] for item in self.client.get("/api/conversations").json()], before_ids)

    def test_legacy_conversation_needs_no_migration(self) -> None:
        json_store.add_item("conversations.json", {"id": "legacy", "title": "旧名称"})
        response = self.client.patch("/api/conversations/legacy/title", json={"title": "新名称"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"id": "legacy", "title": "新名称"})

    def test_concurrent_scope_and_activity_updates_preserve_title(self) -> None:
        json_store.add_item("documents.json", {"id": "a", "status": "indexed"})
        scope = {"mode": "selected", "document_ids": ["a"]}
        conversation_id = self.conversation["id"]
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(chat_service.rename_conversation, conversation_id, "分析主题"),
                executor.submit(chat_service.update_document_scope, conversation_id, scope, 0),
                executor.submit(chat_service._touch_conversation, conversation_id),
            ]
            for future in futures:
                future.result()
        stored = json_store.get_item("conversations.json", conversation_id)
        self.assertEqual(stored["title"], "分析主题")
        self.assertEqual(stored["document_scope"], scope)
        self.assertEqual(stored["scope_revision"], 1)
        resumed = chat_service._get_or_create_conversation(conversation_id, "新的聊天问题")
        chat_service._add_message(conversation_id, "user", "新的聊天问题", [], scope_context=resumed)
        chat_service._touch_conversation(conversation_id)
        self.assertEqual(chat_service.get_conversation(conversation_id)["title"], "分析主题")


if __name__ == "__main__":
    unittest.main()
