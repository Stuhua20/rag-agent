from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.budget import RunBudget
from app.agents.knowledge_qa.runtime import RunContext
from app.core.config import settings
from app.routers.documents import router as document_router
from app.routers.settings import router as settings_router
from app.services.document_pipeline import document_pipeline
from app.services.embedding_service import embedding_service
from app.services.json_store_service import json_store
from app.services.retrieval_index_service import IndexChanged, retrieval_index_service
from app.services.retrieval_service import retrieval_service


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(json_store, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "storage_dir", tmp_path / "original")
    json_store.initialize()
    config = json_store.read_json("settings.json")
    config["embedding"]["mock"] = True
    config["retrieval"].update(search_mode="keyword", chunk_size=80, overlap=0)
    json_store.write_json("settings.json", config)
    app = FastAPI()
    app.include_router(document_router)
    app.include_router(settings_router)
    with TestClient(app) as client:
        response = client.post("/api/documents/upload", files={"file": ("contract.csv", "编号,条款\nZX-001,交货后三十天付款\nZX-002,货物保修两年\n".encode(), "text/csv")})
        assert response.status_code == 200, response.text
        yield client, response.json()["document_id"]


def artifacts():
    return {name: json_store.read_json(name) for name in ("documents.json", "sheets.json", "chunks.json", "embeddings.json")}


def test_upload_reindex_and_delete_refresh_real_indexes(library):
    client, doc_id = library
    old = retrieval_index_service.get()
    original_bytes = next(settings.storage_dir.iterdir()).read_bytes()
    assert retrieval_service.search("ZX-001")
    response = client.post(f"/api/documents/{doc_id}/reindex")
    assert response.status_code == 200, response.text
    new = retrieval_index_service.get()
    assert new is not old
    assert {item["id"] for item in new.chunks}.isdisjoint(item["id"] for item in old.chunks)
    assert all(item["embedding_profile"] == embedding_service.profile() for item in new.embeddings.values())
    assert next(settings.storage_dir.iterdir()).read_bytes() == original_bytes
    assert retrieval_service.search("ZX-001")
    assert client.delete(f"/api/documents/{doc_id}").status_code == 200
    assert retrieval_service.search("ZX-001") == []
    assert not list(settings.storage_dir.iterdir())


def test_reindex_rechunks_using_new_options(library):
    client, doc_id = library
    old_ids = {item["id"] for item in json_store.list_items("chunks.json")}
    config = json_store.read_json("settings.json")
    config["retrieval"]["chunk_size"] = 10
    json_store.write_json("settings.json", config)
    result = client.post(f"/api/documents/{doc_id}/reindex")
    assert result.status_code == 200
    assert result.json()["chunk_count"] == 2
    assert old_ids.isdisjoint(item["id"] for item in json_store.list_items("chunks.json"))


def test_reindex_embedding_failure_preserves_all_old_data(library):
    client, doc_id = library
    before = artifacts()
    with patch.object(embedding_service, "embed_batch", side_effect=RuntimeError("remote failed")):
        response = client.post(f"/api/documents/{doc_id}/reindex")
    assert response.status_code == 500
    assert artifacts() == before
    assert retrieval_service.search("ZX-001")


def test_reindex_partial_publication_failure_rolls_back(library):
    client, doc_id = library
    before = artifacts()
    from app.services import json_store_service as module
    original_replace = module.os.replace
    calls = 0
    def fail_once(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("disk full")
        return original_replace(source, target)
    with patch.object(module.os, "replace", side_effect=fail_once):
        response = client.post(f"/api/documents/{doc_id}/reindex")
    assert response.status_code == 500
    assert artifacts() == before
    assert not list(json_store.data_dir.rglob("*.staged"))
    assert retrieval_service.search("ZX-001")


def test_delete_publication_failure_restores_original_file_and_indexes(library):
    client, doc_id = library
    before = artifacts()
    path = next(settings.storage_dir.iterdir())
    content = path.read_bytes()
    with patch.object(json_store, "write_batch", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            document_pipeline.delete_document(doc_id)
    assert artifacts() == before
    assert path.read_bytes() == content


def test_reindex_concurrent_change_does_not_overwrite_newer_document(library):
    client, doc_id = library
    before = artifacts()
    real_embed = embedding_service.embed_batch
    def embed(texts):
        json_store.update_item("documents.json", doc_id, {"file_name": "renamed.csv"})
        return real_embed(texts)
    with patch.object(embedding_service, "embed_batch", side_effect=embed):
        response = client.post(f"/api/documents/{doc_id}/reindex")
    assert response.status_code == 409
    after = artifacts()
    assert after["documents.json"][0]["file_name"] == "renamed.csv"
    assert all(after[name] == before[name] for name in ("chunks.json", "embeddings.json", "sheets.json"))


def test_reindex_config_change_never_publishes_mixed_vector_space(library):
    client, doc_id = library
    before = artifacts()
    real_embed = embedding_service.embed_batch
    def embed(texts):
        result = real_embed(texts)
        config = json_store.read_json("settings.json")
        config["embedding"]["model"] = "new-space"
        json_store.write_json("settings.json", config)
        return result
    with patch.object(embedding_service, "embed_batch", side_effect=embed):
        response = client.post(f"/api/documents/{doc_id}/reindex")
    assert response.status_code == 409
    assert artifacts() == before


def test_run_context_stops_when_retrieval_settings_change(library):
    client, doc_id = library
    json_store.add_item("conversations.json", {"id": "conversation"})
    context = RunContext(service=None, conversation={"id": "conversation"}, documents={},
                         budget=RunBudget(seconds=30, max_llm_calls=5, max_tool_calls=5), filters={}, top_k=None)
    context.check()
    assert client.put("/api/settings", json={"retrieval": {"score_threshold": 0.7}}).status_code == 200
    with pytest.raises(IndexChanged):
        context.check()


def test_engine_settings_default_validation_and_rollback(library):
    client, doc_id = library
    assert client.get("/api/settings").json()["retrieval"]["engine"] == "bm25_faiss"
    assert client.put("/api/settings", json={"retrieval": {"engine": "unknown"}}).status_code == 422
    assert client.put("/api/settings", json={"retrieval": {"engine": "legacy"}}).status_code == 200
    assert "retrieval_engine" not in retrieval_service.search("ZX-001")[0]
    assert client.put("/api/settings", json={"retrieval": {"engine": "bm25_faiss"}}).status_code == 200
    assert retrieval_service.search("ZX-001")[0]["retrieval_engine"] == "bm25_faiss"


def test_graph_exposes_vector_unavailable_without_publishing_answer(library, monkeypatch):
    client, doc_id = library
    from app.services.chat_service import ChatService
    from app.services.query_understanding_service import query_understanding_service
    config = json_store.read_json("settings.json")
    config["retrieval"]["search_mode"] = "vector"
    config["llm"]["mock"] = True
    json_store.write_json("settings.json", config)
    monkeypatch.setattr(settings, "chat_runtime", "langgraph")
    plan = {"intent": "lookup", "sub_queries": ["付款条件"], "retrieval_queries": ["付款条件"]}
    service = ChatService()
    try:
        with patch.object(query_understanding_service, "plan", return_value=plan), patch.object(
            embedding_service, "embed_text", side_effect=RuntimeError("secret-key"),
        ):
            events = list(service.ask_stream("付款条件"))
        assert events[-1]["event"] == "error"
        assert events[-1]["data"]["code"] == "retrieval_unavailable"
        assert "向量检索不可用" in events[-1]["data"]["message"]
        assert "secret-key" not in str(events)
        assert not any(event["event"] == "done" for event in events)
    finally:
        service.close()


@pytest.mark.parametrize("streaming", [False, True])
def test_legacy_chat_does_not_save_answer_after_config_change(library, monkeypatch, streaming):
    from app.services.chat_service import ChatService
    from app.services.llm_service import llm_service
    from app.services.query_understanding_service import query_understanding_service
    monkeypatch.setattr(settings, "chat_runtime", "legacy")
    service = ChatService()
    def change_config(*args, **kwargs):
        config = json_store.read_json("settings.json")
        config["retrieval"]["score_threshold"] = 0.9
        json_store.write_json("settings.json", config)
        return "交货后三十天付款。"
    def stream(*args, **kwargs):
        yield change_config()
    plan = {"intent": "lookup", "sub_queries": ["ZX-001"], "retrieval_queries": ["ZX-001"]}
    try:
        with patch.object(query_understanding_service, "plan", return_value=plan), patch.object(
            llm_service, "generate_answer", side_effect=change_config,
        ), patch.object(llm_service, "generate_answer_stream", side_effect=stream):
            with pytest.raises(IndexChanged):
                if streaming:
                    list(service.ask_stream("ZX-001"))
                else:
                    service.ask("ZX-001")
        assert not any(item["role"] == "assistant" for item in json_store.list_items("messages.json"))
    finally:
        service.close()
