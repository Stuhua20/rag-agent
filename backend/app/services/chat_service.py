from app.services.json_store_service import json_store
from app.services.llm_service import llm_service
from app.services.retrieval_service import retrieval_service
from app.utils.id_utils import new_id
from app.utils.time_utils import utc_now_iso


NO_SOURCE_ANSWER = "知识库中未找到明确依据。"


class ChatService:
    def ask(
        self,
        question: str,
        conversation_id: str | None = None,
        top_k: int | None = None,
        filters: dict | None = None,
    ) -> dict:
        conversation = self._get_or_create_conversation(conversation_id, question)
        self._add_message(conversation["id"], "user", question, [])

        sources = retrieval_service.search(question, top_k=top_k, filters=filters)
        answer = NO_SOURCE_ANSWER if not sources else llm_service.generate_answer(self._build_prompt(question, sources))
        self._add_message(conversation["id"], "assistant", answer, sources)
        self._touch_conversation(conversation["id"])

        return {"conversation_id": conversation["id"], "answer": answer, "sources": sources}

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

    def _add_message(self, conversation_id: str, role: str, content: str, sources: list[dict]) -> dict:
        message = {
            "id": new_id("msg"),
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "sources": sources,
            "created_at": utc_now_iso(),
        }
        return json_store.add_item("messages.json", message)

    def _touch_conversation(self, conversation_id: str) -> None:
        json_store.update_item("conversations.json", conversation_id, {"updated_at": utc_now_iso()})

    def _build_prompt(self, question: str, sources: list[dict]) -> str:
        context = "\n\n".join(self._format_source(index, source) for index, source in enumerate(sources, start=1))
        return f"""你是企业 Excel 知识库助手。

请严格根据【已检索表格资料】回答用户问题。
如果资料中没有明确答案，请回答“知识库中未找到明确依据”。
不要编造资料中没有的信息。
回答要简洁清楚。
如果涉及数字，请优先引用表格中的原始值。
回答最后必须列出参考来源。

【已检索表格资料】
{context}

【用户问题】
{question}
"""

    def _format_source(self, index: int, source: dict) -> str:
        return f"""[来源 {index}]
文件名：{source.get("file_name", "")}
Sheet：{source.get("sheet_name", "")}
行号：{source.get("row_start")}-{source.get("row_end")}
内容：{source.get("content", "")}"""


chat_service = ChatService()
