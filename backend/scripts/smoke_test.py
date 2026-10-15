import asyncio
import sys
from pathlib import Path

from fastapi import UploadFile
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.main import app  # noqa: E402
from app.services.chat_service import chat_service  # noqa: E402
from app.services.document_pipeline import document_pipeline  # noqa: E402
from app.services.json_store_service import json_store  # noqa: E402


async def main() -> None:
    json_store.initialize()
    original_settings = json_store.read_json("settings.json")
    test_settings = {
        **original_settings,
        "embedding": {**original_settings.get("embedding", {}), "mock": True},
        "llm": {**original_settings.get("llm", {}), "mock": True},
    }
    json_store.write_json("settings.json", test_settings)
    sample_path = ROOT / "samples" / "sales_sample.csv"
    if not sample_path.exists():
        raise FileNotFoundError(f"Missing sample file: {sample_path}")

    document_id = None
    conversation_ids = []
    try:
        with sample_path.open("rb") as file:
            upload = UploadFile(file=file, filename=sample_path.name)
            upload_result = await document_pipeline.upload_and_parse(
                upload,
                sample_path.name,
            )
        document_id = upload_result["document_id"]
        assert upload_result["status"] == "indexed", upload_result
        assert upload_result["chunk_count"] > 0, upload_result

        client = TestClient(app)
        response = client.post(
            "/api/chat",
            json={
                "question": "上海甲公司的销售额是多少？",
                "top_k": 3,
            },
        )
        response.raise_for_status()
        body = response.json()
        conversation_ids.append(body["conversation_id"])
        assert body["sources"], body
        assert "甲公司" in body["answer"], body["answer"]
        assert len(chat_service.list_messages(body["conversation_id"])) == 2

        no_source_response = client.post(
            "/api/chat",
            json={
                "question": "火星基地库存是多少？",
                "top_k": 3,
            },
        )
        no_source_response.raise_for_status()
        no_source_body = no_source_response.json()
        conversation_ids.append(no_source_body["conversation_id"])
        assert no_source_body["sources"] == [], no_source_body
        assert no_source_body["answer"] == "知识库中未找到明确依据。", no_source_body["answer"]
        print("smoke test passed")
    finally:
        for conversation_id in conversation_ids:
            chat_service.delete_conversation(conversation_id)
        if document_id:
            document_pipeline.delete_document(document_id)
        json_store.write_json("settings.json", original_settings)


if __name__ == "__main__":
    asyncio.run(main())
