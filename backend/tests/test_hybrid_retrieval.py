"""Exercise real BM25 and FAISS with deterministic vectors, without remote models."""
import math
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from app.agents.budget import BudgetExceeded, RunCancelled
from app.services.answer_quality_service import answer_quality_service
from app.services.embedding_service import embedding_service
from app.services.json_store_service import json_store
from app.services.retrieval_index_service import IndexChanged, retrieval_index_service, tokenize
from app.services.retrieval_service import retrieval_service
from app.utils.similarity import cosine_similarity


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setattr(json_store, "data_dir", tmp_path / "data")
    from app.core.config import settings
    monkeypatch.setattr(settings, "storage_dir", tmp_path / "storage")
    json_store.initialize()
    config = json_store.read_json("settings.json")
    config["embedding"].update(mock=False, model="test-vector-space")
    config["retrieval"].update(top_k=10, max_chunks_per_doc=0, score_threshold=0.2)
    json_store.write_json("settings.json", config)
    monkeypatch.setattr(embedding_service, "embed_text", lambda text: [1.0, 0.0, 0.0])

    def add(chunk_id, content, vector=None, document_id=None, sheet="合同", **fields):
        doc_id = document_id or chunk_id
        if json_store.get_item("documents.json", doc_id) is None:
            json_store.add_item("documents.json", {"id": doc_id, "status": "indexed", "file_name": doc_id + ".csv"})
        chunk = {"id": chunk_id, "document_id": doc_id, "sheet_id": doc_id + sheet,
                 "sheet_name": sheet, "row_start": 1, "row_end": 1, "content": content,
                 "metadata": {"file_name": doc_id + ".csv", "sheet_name": sheet}, **fields}
        json_store.add_item("chunks.json", chunk)
        if vector is not None:
            json_store.add_item("embeddings.json", {"chunk_id": chunk_id, "document_id": doc_id,
                                 "vector": vector, "embedding_model": "test-vector-space",
                                 "embedding_profile": embedding_service.profile()})
        return chunk

    return add


def configure(**updates):
    config = json_store.read_json("settings.json")
    config["retrieval"].update(updates)
    json_store.write_json("settings.json", config)


def test_hybrid_combines_distinct_keyword_and_semantic_hits(corpus):
    corpus("lexical", "合同 ZX-2026-019 的付款条款", [0.0, 1.0, 0.0])
    corpus("semantic", "应在货物验收完成后的三十日内支付款项", [1.0, 0.0, 0.0])
    corpus("noise", "办公室咖啡库存", [0.0, 0.0, 1.0])
    results = retrieval_service.search("ZX-2026-019")
    assert {item["chunk_id"] for item in results} == {"lexical", "semantic"}
    by_id = {item["chunk_id"]: item for item in results}
    assert by_id["lexical"]["retrieval_methods"] == ["bm25"]
    assert by_id["semantic"]["retrieval_methods"] == ["faiss"]
    assert all(item["score_type"] == "rrf" and item["score"] < 0.2 for item in results)
    report = answer_quality_service.evaluate_evidence("ZX-2026-019", {"intent": "lookup"}, results, {})
    assert report["passed"]  # RRF values must not be compared with the cosine threshold.


def test_rrf_rewards_agreement_and_preserves_raw_metrics(corpus):
    corpus("both", "warranty warranty warranty repair service", [1.0, 0.0, 0.0])
    corpus("dense", "产品可享售后服务", [0.9, 0.1, 0.0])
    corpus("lexical", "warranty maintenance", [0.0, 1.0, 0.0])
    for i in range(3):
        corpus(f"noise-{i}", "coffee inventory", [0.0, 0.0, 1.0])
    results = retrieval_service.search("warranty")
    assert results[0]["chunk_id"] == "both"
    assert math.isclose(results[0]["score"], 2 / 61, abs_tol=1e-8)
    assert results[0]["bm25_rank"] == results[0]["vector_rank"] == 1
    assert results[0]["bm25_score"] is not None
    assert results[0]["vector_score"] == 1.0


def test_faiss_matches_reference_cosine_and_keyword_mode_never_embeds(corpus):
    vectors = [[2, 0, 0], [2, 1, 0], [0, 0, 3]]
    for i, vector in enumerate(vectors):
        corpus(str(i), "售后 warranty", vector)
    configure(search_mode="vector", score_threshold=0)
    results = retrieval_service.search("售后")
    assert [item["chunk_id"] for item in results] == ["0", "1", "2"]
    for item in results:
        assert item["vector_score"] == pytest.approx(cosine_similarity([1, 0, 0], vectors[int(item["chunk_id"])]), abs=1e-6)
    configure(search_mode="keyword")
    with patch.object(embedding_service, "embed_text", side_effect=AssertionError("unexpected model call")):
        assert len(retrieval_service.search("warranty")) == 3


def test_scope_is_applied_before_candidates_and_includes_sheet(corpus):
    for i in range(25):
        corpus(f"outside-{i}", "合同付款条款付款条款", [1, 0, 0], sheet="其他")
    corpus("allowed", "付款条款", [0.8, 0.2, 0], document_id="selected", sheet="目标")
    corpus("wrong-sheet", "付款条款", [1, 0, 0], document_id="selected", sheet="其他")
    for mode in ("hybrid", "vector", "keyword"):
        configure(search_mode=mode)
        results = retrieval_service.search("付款条款", top_k=1, filters={"document_ids": ["selected"], "sheet_name": "目标"})
        assert [item["chunk_id"] for item in results] == ["allowed"]
        assert retrieval_service.search("付款条款", filters={"document_ids": []}) == []


def test_single_chunk_negative_idf_and_missing_embeddings_are_searchable(corpus):
    corpus("only", "付款条件为月结")
    configure(search_mode="keyword")
    result = retrieval_service.search("付款条件")
    assert len(result) == 1 and result[0]["is_relevant"]
    assert result[0]["bm25_score"] <= 0
    assert retrieval_service.search("火星飞船") == []
    assert retrieval_service.search("的 是否 what is") == []


def test_metadata_fields_and_identifier_tokenization(corpus):
    corpus("metadata", "请见附件", sheet="经费管理", columns=["项目编号"], title="预算审批")
    configure(search_mode="keyword")
    assert retrieval_service.search("经费管理")
    assert retrieval_service.search("项目编号")
    assert "zx-2026-019" in tokenize("查询 ZX-2026-019 的付款条件")
    assert tokenize("WHAT IS Warranty") == ["warranty"]


def test_multilingual_queries_deduplicate_and_apply_doc_cap_after_fusion(corpus):
    corpus("a1", "付款 payment", [1, 0, 0], document_id="a")
    corpus("a2", "付款 payment", [1, 0, 0], document_id="a")
    corpus("b", "付款 payment", [1, 0, 0], document_id="b")
    configure(max_chunks_per_doc=1)
    one = retrieval_service.search("付款")
    multiple = retrieval_service.search_multiple(["付款", "payment", "payment"])
    assert len(multiple) == 2
    assert len({item["chunk_id"] for item in multiple}) == 2
    assert {item["document_id"] for item in multiple} == {"a", "b"}
    assert max(item["score"] for item in multiple) <= max(item["score"] for item in one)


def test_full_scan_keeps_irrelevant_chunks_and_ignores_limits(corpus):
    for i in range(7):
        corpus(str(i), "付款条件" if i == 0 else "办公室咖啡", [0, 1, 0], document_id="one")
    configure(top_k=1, max_chunks_per_doc=1, score_threshold=0.99)
    results = retrieval_service.search("付款条件", full_scan=True)
    assert len(results) == 7
    assert sum(item["is_relevant"] for item in results) == 1
    assert not any(item["is_relevant"] for item in retrieval_service.search("火星", full_scan=True))


def test_full_scan_multiquery_preserves_negative_keyword_match_metadata(corpus):
    corpus("one", "付款条件")
    configure(search_mode="keyword")
    result = retrieval_service.search_multiple(["付款条件", "火星"], full_scan=True)[0]
    assert result["is_relevant"]
    assert result["retrieval_methods"] == ["bm25"]
    assert result["bm25_score"] is not None


def test_config_change_between_config_read_and_index_acquisition_aborts(corpus):
    corpus("one", "付款", [1, 0, 0])
    original_get = retrieval_index_service.get
    def get(filters):
        configure(score_threshold=0.8)
        return original_get(filters)
    with patch.object(retrieval_index_service, "get", side_effect=get):
        with pytest.raises(IndexChanged):
            retrieval_service.search("付款")


def test_index_reuse_invalidation_and_bounded_cache(corpus):
    corpus("first", "付款", [1, 0, 0])
    first = retrieval_index_service.get()
    with patch.object(embedding_service, "embed_batch", side_effect=AssertionError("must reuse saved vectors")):
        assert retrieval_index_service.get() is first
    corpus("second", "质保", [0, 1, 0])
    second = retrieval_index_service.get()
    assert second is not first and len(second.chunks) == 2
    with pytest.raises(IndexChanged):
        retrieval_index_service.assert_current(first.version)
    for i in range(12):
        retrieval_index_service.get({"document_ids": [str(i)]})
    assert len(retrieval_index_service._cache) <= 8


def test_embedding_failure_degrades_hybrid_but_not_vector_and_hides_error(corpus):
    corpus("one", "付款条款", [1, 0, 0])
    with patch.object(embedding_service, "embed_text", side_effect=RuntimeError("secret-api-token")):
        result = retrieval_service.search("付款条款")
        assert result[0]["retrieval_methods"] == ["bm25"]
        assert "降级" in result[0]["retrieval_warning"]
        assert "secret-api-token" not in str(result)
        configure(search_mode="vector")
        with pytest.raises(ValueError, match="向量检索不可用"):
            retrieval_service.search("付款条款")


@pytest.mark.parametrize("failure", [BudgetExceeded("budget"), RunCancelled("cancelled")])
def test_budget_and_cancellation_never_degrade(corpus, failure):
    corpus("one", "付款", [1, 0, 0])
    with patch.object(embedding_service, "embed_text", side_effect=failure):
        with pytest.raises(type(failure)):
            retrieval_service.search("付款")


def test_model_change_rejects_vectors_even_if_dimension_matches(corpus):
    corpus("one", "付款", [1, 0, 0])
    config = json_store.read_json("settings.json")
    config["embedding"]["model"] = "different-model"
    json_store.write_json("settings.json", config)
    result = retrieval_service.search("付款")
    assert result[0]["retrieval_methods"] == ["bm25"]
    assert result[0]["retrieval_warning"]
    configure(search_mode="vector")
    with pytest.raises(ValueError):
        retrieval_service.search("付款")


def test_legacy_vector_without_profile_requires_reindex(corpus):
    corpus("one", "付款", [1, 0, 0])
    embeddings = json_store.list_items("embeddings.json")
    embeddings[0].pop("embedding_profile")
    json_store.write_json("embeddings.json", embeddings)
    result = retrieval_service.search("付款")
    assert result[0]["retrieval_methods"] == ["bm25"]
    assert "降级" in result[0]["retrieval_warning"]


@pytest.mark.parametrize("vector", [[1, 2], [float("nan"), 0, 0], [0, 0, 0]])
def test_invalid_query_vectors_do_not_reach_faiss(corpus, vector):
    corpus("one", "付款", [1, 0, 0])
    with patch.object(embedding_service, "embed_text", return_value=vector):
        result = retrieval_service.search("付款")
    assert result[0]["retrieval_methods"] == ["bm25"]


def test_index_build_cannot_publish_after_data_changes(corpus):
    corpus("one", "付款", [1, 0, 0])
    # Change data during an off-lock build, after the initial version was captured.
    from app.services import retrieval_index_service as module
    real_tokenize = module.tokenize
    def mutate(text):
        corpus("two", "交货", [0, 1, 0])
        return real_tokenize(text)
    with patch.object(module, "tokenize", side_effect=mutate):
        with pytest.raises(IndexChanged):
            retrieval_index_service.get()
    assert len(retrieval_index_service.get().chunks) == 2


def test_concurrent_scoped_queries_do_not_share_results(corpus):
    for i in range(4):
        corpus(str(i), "付款条款", [1, 0, 0])
    def search(i):
        return retrieval_service.search("付款条款", filters={"document_ids": [str(i)]})
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(search, range(4)))
    assert [[item["document_id"] for item in result] for result in results] == [[str(i)] for i in range(4)]


def test_legacy_engine_is_explicit_and_historical_scores_still_work(corpus):
    corpus("one", "付款条款", [1, 0, 0])
    configure(engine="legacy", search_mode="keyword")
    results = retrieval_service.search("付款条款")
    assert results and "retrieval_engine" not in results[0]
    assert retrieval_service.is_relevant_source(results[0])
    assert retrieval_service.is_relevant_source({"score_type": "exact_match", "score": 0})
    assert not retrieval_service.is_relevant_source({"score": "invalid"})
    assert not retrieval_service.is_relevant_source({"score": 1, "is_relevant": False})
