"""Repeatable, side-effect-limited checks for the P0-2/3/4 changes."""

from __future__ import annotations

import asyncio
import io
import sys
import tempfile
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import UploadFile
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.settings import SettingsPayload
from app.services.chat_service import chat_service
from app.services.document_pipeline import document_pipeline
from app.services.embedding_service import embedding_service
from app.services.json_store_service import DEFAULT_SETTINGS, json_store
from app.services.llm_service import llm_service
from app.services.query_understanding_service import query_understanding_service
from app.services.retrieval_service import retrieval_service
from app.services.table_analysis_service import table_analysis_service


def check_defaults_and_validation() -> None:
    assert DEFAULT_SETTINGS["embedding"]["normalize"] is True
    assert DEFAULT_SETTINGS["retrieval"]["search_mode"] == "hybrid"
    assert DEFAULT_SETTINGS["retrieval"]["full_scan_max_chunks"] >= 1

    try:
        SettingsPayload(retrieval={"top_k": 0})
    except ValidationError:
        pass
    else:
        raise AssertionError("invalid retrieval settings were accepted")

    payload = SettingsPayload(
        retrieval={"chunk_size": 100, "overlap": 20, "search_mode": "keyword"}
    )
    assert payload.retrieval is not None
    assert payload.retrieval.chunk_size == 100
    assert payload.retrieval.overlap == 20
    assert payload.retrieval.search_mode == "keyword"


def check_query_routing() -> None:
    lookup_plan = {"intent": "lookup", "retrieval": {"need_full_scan": False}}
    assert not query_understanding_service.needs_full_scan("销售额是多少", lookup_plan)
    assert query_understanding_service.needs_full_scan("销售额总计", lookup_plan)
    assert query_understanding_service.needs_full_scan("客户按销售额排名", lookup_plan)
    assert not query_understanding_service.needs_full_scan(
        "销售额是多少", {"intent": "summary", "retrieval": {"need_full_scan": False}}
    )


def check_query_expansion() -> None:
    fallback = query_understanding_service._fallback_plan("收入是多少？", {}, None)
    normalized = query_understanding_service._normalize_plan(
        {
            "intent": "lookup",
            "sub_queries": ["收入是多少？"],
            "retrieval_queries": ["What is the revenue?"],
            "filters": {},
            "retrieval": {},
        },
        fallback,
        {},
        None,
    )
    assert normalized["retrieval_queries"] == ["收入是多少？", "What is the revenue?"]
    assert fallback["retrieval_queries"] == ["收入是多少？"]

    original_generate = llm_service.generate_answer
    try:
        llm_service.generate_answer = lambda prompt: (
            '{"intent":"lookup","sub_queries":["收入是多少？"],'
            '"retrieval_queries":["What is the revenue?"]}'
        )
        planned = query_understanding_service.plan("收入是多少？")
        assert planned["retrieval_queries"] == ["收入是多少？", "What is the revenue?"]
    finally:
        llm_service.generate_answer = original_generate

    original_search = retrieval_service.search_multiple
    original_analysis = table_analysis_service.analyze
    captured_queries = []
    try:
        table_analysis_service.analyze = lambda *args, **kwargs: None
        retrieval_service.search_multiple = lambda queries, **kwargs: captured_queries.extend(queries) or []
        chat_service._prepare_retrieval(
            "收入是多少？",
            {
                "intent": "lookup",
                "sub_queries": ["收入是多少？"],
                "retrieval_queries": ["收入是多少？", "What is the revenue?"],
                "filters": {},
                "retrieval": {"need_full_scan": False},
            },
            3,
            None,
        )
        assert captured_queries == ["收入是多少？", "What is the revenue?"]
    finally:
        retrieval_service.search_multiple = original_search
        table_analysis_service.analyze = original_analysis


def check_bilingual_query_expansion() -> None:
    original_generate = llm_service.generate_answer
    calls = []

    def generate_answer(prompt):
        calls.append(prompt)
        if "查询翻译模块" in prompt:
            if "English" in prompt:
                return '["What are the respective functions of MSDC, DACG, and ACP?"]'
            return '["MSDC、DACG 和 ACP 分别有什么作用？"]'
        if "What are the respective functions of MSDC, DACG, and ACP?" in prompt:
            return (
                '{"intent":"lookup","sub_queries":["What are the respective functions of MSDC, DACG, and ACP?"],'
                '"retrieval_queries":[]}'
            )
        return (
            '{"intent":"lookup","sub_queries":["MSDC、DACG、ACP 分别有什么作用？"],'
            '"retrieval_queries":[]}'
        )

    try:
        llm_service.generate_answer = generate_answer
        chinese_plan = query_understanding_service.plan("MSDC、DACG、ACP 分别有什么作用？")
        assert chinese_plan["retrieval_queries"] == [
            "MSDC、DACG、ACP 分别有什么作用？",
            "What are the respective functions of MSDC, DACG, and ACP?",
        ]

        english_plan = query_understanding_service.plan(
            "What are the respective functions of MSDC, DACG, and ACP?"
        )
        assert english_plan["retrieval_queries"] == [
            "What are the respective functions of MSDC, DACG, and ACP?",
            "MSDC、DACG 和 ACP 分别有什么作用？",
        ]
        assert len(calls) == 4
    finally:
        llm_service.generate_answer = original_generate


def check_multilingual_full_scan() -> None:
    original_search = retrieval_service.search
    calls = []

    def search(query, **kwargs):
        calls.append(query)
        return [
            {
                "chunk_id": f"chunk-{len(calls)}",
                "document_id": "doc-test",
                "score": 0.8,
                "vector_score": 0.8,
                "keyword_score": 0.0,
            }
        ]

    try:
        retrieval_service.search = search
        sources = retrieval_service.search_multiple(
            ["中文问题", "English question"],
            top_k=3,
            full_scan=True,
        )
        assert calls == ["中文问题", "English question"]
        assert len(sources) == 2
    finally:
        retrieval_service.search = original_search


def check_deterministic_table_analysis() -> None:
    original_data_dir = json_store.data_dir
    try:
        with tempfile.TemporaryDirectory(prefix="p0-analysis-") as temp_dir:
            json_store.data_dir = Path(temp_dir)
            json_store.initialize()
            json_store.write_json(
                "documents.json",
                [
                    {
                        "id": "doc-test",
                        "file_name": "sales.csv",
                        "status": "indexed",
                        "permission_level": 1,
                    }
                ],
            )
            json_store.write_json(
                "chunks.json",
                [
                    {
                        "id": "chunk-test-1",
                        "document_id": "doc-test",
                        "sheet_id": "sheet-test",
                        "sheet_name": "sales",
                        "row_start": 2,
                        "row_end": 3,
                        "columns": ["地区", "客户", "销售额"],
                        "content": (
                            "文件：sales.csv\n"
                            "Sheet：sales\n"
                            "行 2：地区=上海；客户=甲公司；销售额=120000\n"
                            "行 3：地区=上海；客户=乙公司；销售额=76000"
                        ),
                        "metadata": {},
                    },
                    {
                        "id": "chunk-test-2",
                        "document_id": "doc-test",
                        "sheet_id": "sheet-test",
                        "sheet_name": "sales",
                        "row_start": 3,
                        "row_end": 4,
                        "columns": ["地区", "客户", "销售额"],
                        "content": (
                            "文件：sales.csv\n"
                            "Sheet：sales\n"
                            "行 3：地区=上海；客户=乙公司；销售额=76000\n"
                            "行 4：地区=北京；客户=甲公司；销售额=97000"
                        ),
                        "metadata": {},
                    },
                ],
            )

            total = table_analysis_service.analyze(
                "销售额总计", "summary", {"sheet_name": "sales"}
            )
            assert total is not None
            assert "293000" in total["answer"]
            assert total["chunk_ids"] == ["chunk-test-1", "chunk-test-2"]

            sources, deterministic_answer, retrieval_state = chat_service._prepare_retrieval(
                "销售额总计",
                {
                    "intent": "summary",
                    "sub_queries": ["销售额总计"],
                    "filters": {"sheet_name": "sales"},
                    "retrieval": {"top_k": None, "need_full_scan": False},
                },
                3,
                {"sheet_name": "sales"},
            )
            assert deterministic_answer == total["answer"]
            assert len(sources) == 2
            assert all(source["score_type"] == "exact_match" for source in sources)
            assert retrieval_state == {
                "full_scan_required": True,
                "full_scan_complete": True,
                "deterministic": True,
            }

            ranking = table_analysis_service.analyze(
                "销售额最高的客户", "ranking", {"sheet_name": "sales"}
            )
            assert ranking is not None
            assert "甲公司" in ranking["answer"]
            assert "217000" in ranking["answer"]

            json_store.write_json(
                "documents.json",
                [
                    {
                        "id": "doc-en",
                        "file_name": "revenue.csv",
                        "status": "indexed",
                        "permission_level": 1,
                    }
                ],
            )
            json_store.write_json(
                "chunks.json",
                [
                    {
                        "id": "chunk-en-1",
                        "document_id": "doc-en",
                        "sheet_id": "sheet-en",
                        "sheet_name": "revenue",
                        "row_start": 2,
                        "row_end": 3,
                        "content": (
                            "文件：revenue.csv\n"
                            "Sheet：revenue\n"
                            "行 2：Region=Shanghai；Revenue=120\n"
                            "行 3：Region=Beijing；Revenue=80"
                        ),
                        "metadata": {},
                    }
                ],
            )
            bilingual_total = table_analysis_service.analyze(
                "收入总计是多少？",
                "summary",
                query_variants=["What is the total revenue?"],
            )
            assert bilingual_total is not None
            assert "Revenue合计为 200" in bilingual_total["answer"]
            assert bilingual_total["chunk_ids"] == ["chunk-en-1"]
    finally:
        json_store.data_dir = original_data_dir


def check_vector_count_guard() -> None:
    original_embed_batch = embedding_service.embed_batch
    try:
        embedding_service.embed_batch = lambda texts: []
        try:
            document_pipeline._create_embeddings(
                [{"id": "chunk-test", "document_id": "doc-test", "content": "test"}],
            )
        except ValueError as exc:
            assert "count mismatch" in str(exc)
        else:
            raise AssertionError("embedding count mismatch was not rejected")
    finally:
        embedding_service.embed_batch = original_embed_batch


def check_upload_limit_and_cleanup() -> None:
    original_data_dir = json_store.data_dir
    original_storage_dir = settings.storage_dir
    original_max_upload_mb = settings.max_upload_mb
    try:
        with tempfile.TemporaryDirectory(prefix="p0-upload-") as temp_dir:
            temp_path = Path(temp_dir)
            json_store.data_dir = temp_path / "data"
            settings.storage_dir = temp_path / "storage"
            settings.max_upload_mb = 1
            json_store.initialize()

            upload = UploadFile(
                file=io.BytesIO(b"x" * (1024 * 1024 + 1)),
                filename="large.csv",
            )
            try:
                asyncio.run(document_pipeline.upload_and_parse(upload, None, 1))
            except ValueError as exc:
                assert "exceeds" in str(exc)
            else:
                raise AssertionError("oversized upload was accepted")

            failed_docs = json_store.list_items("documents.json")
            assert len(failed_docs) == 1
            assert failed_docs[0]["status"] == "failed"
            assert json_store.list_items("sheets.json") == []
            assert json_store.list_items("chunks.json") == []
            assert json_store.list_items("embeddings.json") == []
            assert not any(settings.storage_dir.iterdir())
    finally:
        json_store.data_dir = original_data_dir
        settings.storage_dir = original_storage_dir
        settings.max_upload_mb = original_max_upload_mb


def check_chat_service_wiring() -> None:
    assert callable(chat_service._prepare_retrieval)


def main() -> None:
    check_defaults_and_validation()
    check_query_routing()
    check_query_expansion()
    check_bilingual_query_expansion()
    check_multilingual_full_scan()
    check_deterministic_table_analysis()
    check_vector_count_guard()
    check_upload_limit_and_cleanup()
    check_chat_service_wiring()
    print("p0 self-check passed")


if __name__ == "__main__":
    main()
