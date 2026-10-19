import re
import logging
from collections import defaultdict

import faiss
import numpy as np

from app.core.config import settings
from app.services.embedding_service import embedding_service
from app.services.json_store_service import json_store
from app.utils.similarity import cosine_similarity
from app.agents.budget import BudgetExceeded, RunCancelled, check_budget
from app.services.retrieval_index_service import IndexSnapshot, VectorSearchUnavailable, retrieval_index_service, tokenize


logger = logging.getLogger(__name__)


QUESTION_WORDS = (
    "有哪些",
    "有什么",
    "是什么",
    "是多少",
    "哪些",
    "什么",
    "多少",
    "请问",
    "一下",
    "是否",
    "吗",
    "呢",
    "的",
)


class RetrievalService:
    def search(
        self, question: str, top_k: int | None = None, filters: dict | None = None,
        full_scan: bool = False,
    ) -> list[dict]:
        return self.search_multiple([question], top_k=top_k, filters=filters, full_scan=full_scan)

    def search_multiple(
        self, queries: list[str], top_k: int | None = None, filters: dict | None = None,
        full_scan: bool = False,
    ) -> list[dict]:
        with json_store._lock:
            config = self._get_config()
            version = retrieval_index_service.version()
        if config["engine"] == "legacy":
            sources = self._legacy_search_multiple(queries, top_k, filters, full_scan)
            retrieval_index_service.assert_current(version)
            return sources
        snapshot = retrieval_index_service.get(filters)
        retrieval_index_service.assert_current(version)
        normalized = list(dict.fromkeys(str(query).strip() for query in (queries or []) if str(query).strip())) or [""]
        limit = top_k or config["top_k"]
        candidates = min(len(snapshot.chunks), max(20, 3 * limit))
        primary_language = self._query_language(normalized[0])
        merged = {}
        for query in normalized:
            check_budget()
            results = self._search_snapshot(query, snapshot, config, candidates, full_scan)
            weight = self._query_weight(primary_language, self._query_language(query))
            for source in results:
                source["score"] = round(source["score"] * weight, 8)
                chunk_id = source["chunk_id"]
                previous = merged.get(chunk_id)
                if previous is None or (source["is_relevant"], source["score"]) > (previous["is_relevant"], previous["score"]):
                    merged[chunk_id] = source
        retrieval_index_service.assert_current(snapshot.version)
        sources = sorted(merged.values(), key=lambda item: (
            -int(item["is_relevant"]) if full_scan else 0, -item["score"], item["chunk_id"],
        ))
        if full_scan:
            return sources
        if config["max_chunks_per_doc"] > 0:
            sources = self._limit_per_document(sources, config["max_chunks_per_doc"])
        return sources[:limit]

    def _search_snapshot(
        self, question: str, snapshot: IndexSnapshot, config: dict, candidates: int, full_scan: bool,
    ) -> list[dict]:
        if not snapshot.chunks:
            return []
        mode = config["search_mode"]
        bm25_scores, vector_scores = {}, {}
        bm25_rows, vector_rows = [], []
        reason = ""
        if mode != "vector" and snapshot.bm25 is not None:
            terms = tokenize(question)
            scores = snapshot.bm25.get_scores(terms)
            matching = [row for row, tokens in enumerate(snapshot.tokens) if tokens.intersection(terms)]
            bm25_scores = {row: float(scores[row]) for row in matching}
            bm25_rows = sorted(matching, key=lambda row: (-bm25_scores[row], snapshot.chunks[row]["id"]))
            if not full_scan:
                bm25_rows = bm25_rows[:candidates]
        if mode != "keyword":
            if snapshot.incompatible_chunks:
                reason = "部分片段缺少兼容向量，需要重新索引；关键词检索仍可使用。"
            try:
                if snapshot.vector_index is None:
                    raise ValueError("当前范围没有兼容的向量，请重新索引文档。")
                query = np.asarray(embedding_service.embed_text(question), dtype="float32")
                if (query.ndim != 1 or query.size != snapshot.dimension
                        or not np.isfinite(query).all() or np.linalg.norm(query) == 0):
                    raise ValueError("查询向量维度或数值无效，请检查 Embedding 配置并重新索引。")
                query = np.ascontiguousarray(query.reshape(1, -1))
                faiss.normalize_L2(query)
                count = len(snapshot.vector_rows) if full_scan else min(candidates, len(snapshot.vector_rows))
                distances, indices = snapshot.vector_index.search(query, count)
                for score, index in zip(distances[0], indices[0]):
                    if index >= 0:
                        row = snapshot.vector_rows[int(index)]
                        vector_scores[row] = float(score)
                vector_rows = sorted((row for row, score in vector_scores.items() if score >= config["score_threshold"]),
                                     key=lambda row: (-vector_scores[row], snapshot.chunks[row]["id"]))
            except (BudgetExceeded, RunCancelled):
                raise
            except Exception as exc:
                if mode == "vector":
                    logger.warning("Vector retrieval unavailable (%s)", type(exc).__name__)
                    raise VectorSearchUnavailable("向量检索不可用，请检查 Embedding 服务或重新索引文档。") from None
                # Do not include API errors or credentials in citation metadata/logs.
                reason = "向量检索不可用，本次已降级为 BM25 关键词检索。"
                logger.warning("Hybrid retrieval degraded to BM25 (%s)", type(exc).__name__)
        bm25_ranks = {row: rank for rank, row in enumerate(bm25_rows, 1)}
        vector_ranks = {row: rank for rank, row in enumerate(vector_rows, 1)}
        selected = range(len(snapshot.chunks)) if full_scan else set(bm25_rows) | set(vector_rows)
        sources = []
        for row in selected:
            check_budget()
            chunk = snapshot.chunks[row]
            methods = (["bm25"] if row in bm25_ranks else []) + (["faiss"] if row in vector_ranks else [])
            if mode == "keyword":
                score, score_type = bm25_scores.get(row, 0.0), "bm25"
            elif mode == "vector":
                score, score_type = vector_scores.get(row, 0.0), "similarity"
            else:
                score = sum(1.0 / (60 + ranks[row]) for ranks in (bm25_ranks, vector_ranks) if row in ranks)
                score_type = "rrf"
            source = self._source_from_chunk(
                chunk, chunk.get("metadata", {}), snapshot.embeddings.get(chunk["id"], {}), score, [], set(),
                vector_score=vector_scores.get(row, 0.0), keyword_score=0.0, score_type=score_type,
            )
            source.update(score=round(score, 8), retrieval_engine="bm25_faiss", is_relevant=bool(methods),
                          retrieval_methods=methods, bm25_score=bm25_scores.get(row),
                          bm25_rank=bm25_ranks.get(row), vector_rank=vector_ranks.get(row))
            if reason:
                source["retrieval_warning"] = reason
            sources.append(source)
        return sources

    def is_relevant_source(self, source: dict) -> bool:
        if "is_relevant" in source:
            return source["is_relevant"] is True
        if source.get("score_type") == "exact_match":
            return True
        try:
            return float(source.get("score", 0) or 0) >= self.score_threshold()
        except (TypeError, ValueError):
            return False

    def _legacy_search(
        self,
        question: str,
        top_k: int | None = None,
        filters: dict | None = None,
        full_scan: bool = False,
    ) -> list[dict]:
        config = self._get_config()
        query_vector = self._safe_embed_text(question) if config["search_mode"] != "keyword" else []
        query_terms = self._query_terms(question) if config["search_mode"] != "vector" else set()
        filters = filters or {}
        limit = top_k or config["top_k"]
        threshold = config["score_threshold"]
        max_per_doc = config["max_chunks_per_doc"]
        allowed_ids = set(filters["document_ids"]) if "document_ids" in filters else None
        indexed_document_ids = {
            document.get("id")
            for document in json_store.list_items("documents.json")
            if document.get("status") == "indexed" and (allowed_ids is None or document.get("id") in allowed_ids)
        }
        chunks_by_id = {chunk["id"]: chunk for chunk in json_store.list_items("chunks.json")}
        scored_sources = []

        for embedding in json_store.list_items("embeddings.json"):
            check_budget()
            if embedding.get("document_id") not in indexed_document_ids:
                continue
            chunk = chunks_by_id.get(embedding.get("chunk_id"))
            if not chunk or chunk.get("document_id") not in indexed_document_ids:
                continue

            metadata = {**chunk.get("metadata", {}), **embedding.get("metadata", {})}
            if not self._matches_filters(metadata, filters):
                continue

            vector_score = cosine_similarity(query_vector, embedding.get("vector", []))
            keyword_score = self._keyword_score(query_terms, chunk)

            # 根据 search_mode 计算分数。
            if config["search_mode"] == "vector":
                score = vector_score
            elif config["search_mode"] == "keyword":
                score = keyword_score
            else:  # hybrid
                score = max(vector_score, keyword_score)

            if not full_scan and score < threshold:
                continue

            scored_sources.append(
                self._source_from_chunk(
                    chunk,
                    metadata,
                    embedding,
                    score,
                    query_vector,
                    query_terms,
                    vector_score=vector_score,
                    keyword_score=keyword_score,
                )
            )

        scored_sources.sort(key=lambda item: (-item["score"], item["chunk_id"]))

        # 应用 max_chunks_per_doc 限制
        if not full_scan and max_per_doc > 0:
            scored_sources = self._limit_per_document(scored_sources, max_per_doc)

        return scored_sources if full_scan else scored_sources[:limit]

    def _get_config(self) -> dict:
        settings_json = json_store.read_json("settings.json")
        retrieval_settings = settings_json.get("retrieval", {}) if isinstance(settings_json, dict) else {}
        return {
            "engine": retrieval_settings.get("engine", "bm25_faiss")
            if retrieval_settings.get("engine", "bm25_faiss") in {"bm25_faiss", "legacy"} else "bm25_faiss",
            "top_k": self._as_int(retrieval_settings.get("top_k"), settings.default_top_k, 1),
            "score_threshold": self._as_float(
                retrieval_settings.get("score_threshold"), settings.default_score_threshold, 0.0, 1.0
            ),
            "search_mode": retrieval_settings.get("search_mode", "hybrid")
            if retrieval_settings.get("search_mode", "hybrid") in {"hybrid", "vector", "keyword"}
            else "hybrid",
            "max_chunks_per_doc": self._as_int(retrieval_settings.get("max_chunks_per_doc"), 3, 0),
            "full_scan_max_chunks": self._as_int(
                retrieval_settings.get("full_scan_max_chunks"), settings.full_scan_max_chunks, 1
            ),
        }

    def top_k(self) -> int:
        return self._get_config()["top_k"]

    def full_scan_max_chunks(self) -> int:
        return self._get_config()["full_scan_max_chunks"]

    def score_threshold(self) -> float:
        return self._get_config()["score_threshold"]

    def _as_int(self, value, default: int, minimum: int) -> int:
        try:
            return max(int(value), minimum)
        except (TypeError, ValueError):
            return default

    def _as_float(self, value, default: float, minimum: float, maximum: float) -> float:
        try:
            return min(max(float(value), minimum), maximum)
        except (TypeError, ValueError):
            return default

    def _limit_per_document(self, sources: list[dict], max_per_doc: int) -> list[dict]:
        """限制每个文档返回的 chunk 数量"""
        doc_count = defaultdict(int)
        result = []
        for source in sources:
            doc_id = source["document_id"]
            if doc_count[doc_id] < max_per_doc:
                result.append(source)
                doc_count[doc_id] += 1
        return result

    def _legacy_search_multiple(
        self,
        queries: list[str],
        top_k: int | None = None,
        filters: dict | None = None,
        full_scan: bool = False,
    ) -> list[dict]:
        """对多个查询分别检索，合并去重后返回"""
        config = self._get_config()
        limit = top_k or config["top_k"]

        normalized_queries = list(dict.fromkeys(
            str(query).strip() for query in (queries or []) if str(query).strip()
        )) or [""]
        if len(normalized_queries) == 1:
            return self._legacy_search(
                normalized_queries[0],
                top_k=limit,
                filters=filters,
                full_scan=full_scan,
            )

        source_by_chunk_id = {}
        query_scores = defaultdict(float)
        primary_language = self._query_language(normalized_queries[0])

        for query in normalized_queries:
            query_language = self._query_language(query)
            query_weight = self._query_weight(primary_language, query_language)
            sources = self._legacy_search(
                query,
                top_k=limit,
                filters=filters,
                full_scan=full_scan,
            )
            for source in sources:
                chunk_id = source["chunk_id"]
                existing = source_by_chunk_id.get(chunk_id)
                if existing is None:
                    source_by_chunk_id[chunk_id] = dict(source)
                else:
                    for field in ("vector_score", "keyword_score"):
                        if field in source:
                            existing[field] = max(
                                float(existing.get(field, 0) or 0),
                                float(source.get(field, 0) or 0),
                            )

                query_scores[chunk_id] = max(
                    query_scores[chunk_id],
                    float(source.get("score", 0) or 0) * query_weight,
                )

        all_sources = list(source_by_chunk_id.values())
        for source in all_sources:
            source["score"] = round(query_scores[source["chunk_id"]], 6)
        all_sources.sort(key=lambda item: (-item["score"], item["chunk_id"]))

        # 应用 max_chunks_per_doc 限制
        max_per_doc = config["max_chunks_per_doc"]
        if not full_scan and max_per_doc > 0:
            all_sources = self._limit_per_document(all_sources, max_per_doc)

        return all_sources if full_scan else all_sources[:limit]

    def _query_language(self, query: str) -> str:
        has_cjk = bool(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", query))
        has_latin = bool(re.search(r"[A-Za-z]", query))
        if has_cjk and has_latin:
            return "mixed"
        if has_cjk:
            return "chinese"
        if has_latin:
            return "english"
        return "unknown"

    def _query_weight(self, primary_language: str, query_language: str) -> float:
        """给跨语言补充查询轻微降权，避免翻译噪声压过原始问题。"""
        if primary_language == "unknown" or query_language == "unknown":
            return 1.0
        if primary_language == query_language:
            return 1.0
        return 0.9

    def sources_for_chunk_ids(
        self, chunk_ids: list[str], limit: int | None = None, document_ids: list[str] | None = None,
    ) -> list[dict]:
        """返回确定性分析命中的 chunk，供回答引用。"""
        allowed_ids = set(document_ids) if document_ids is not None else None
        indexed_document_ids = {
            document.get("id")
            for document in json_store.list_items("documents.json")
            if document.get("status") == "indexed" and (allowed_ids is None or document.get("id") in allowed_ids)
        }
        chunks_by_id = {chunk["id"]: chunk for chunk in json_store.list_items("chunks.json")}
        embeddings_by_chunk_id = {
            embedding.get("chunk_id"): embedding
            for embedding in json_store.list_items("embeddings.json")
        }
        sources = []
        for chunk_id in chunk_ids:
            chunk = chunks_by_id.get(chunk_id)
            if not chunk or chunk.get("document_id") not in indexed_document_ids:
                continue
            embedding = embeddings_by_chunk_id.get(chunk_id, {})
            metadata = embedding.get("metadata", {}) or chunk.get("metadata", {})
            source = self._source_from_chunk(chunk, metadata, embedding, 1.0, [], set())
            source["score_type"] = "exact_match"
            sources.append(source)
        return sources if limit is None else sources[:limit]

    def _source_from_chunk(
        self,
        chunk: dict,
        metadata: dict,
        embedding: dict,
        score: float,
        query_vector: list[float],
        query_terms: set[str],
        *,
        vector_score: float | None = None,
        keyword_score: float | None = None,
        score_type: str = "similarity",
    ) -> dict:
        source = {
            "chunk_id": chunk["id"],
            "document_id": chunk["document_id"],
            "sheet_id": chunk["sheet_id"],
            "file_name": metadata.get("file_name", ""),
            "sheet_name": chunk.get("sheet_name", metadata.get("sheet_name", "")),
            "row_start": chunk.get("row_start"),
            "row_end": chunk.get("row_end"),
            "score": round(score, 6),
            "score_type": score_type,
            "vector_score": round(
                vector_score
                if vector_score is not None
                else (cosine_similarity(query_vector, embedding.get("vector", [])) if query_vector else 0),
                6,
            ),
            "keyword_score": round(
                keyword_score
                if keyword_score is not None
                else (self._keyword_score(query_terms, chunk) if query_terms else 0),
                6,
            ),
            "content": chunk.get("content", ""),
        }
        return source

    def _matches_filters(self, metadata: dict, filters: dict) -> bool:
        for key in ("sheet_name",):
            value = filters.get(key)
            if value and metadata.get(key) != value:
                return False
        return True

    def _safe_embed_text(self, question: str) -> list[float]:
        try:
            return embedding_service.embed_text(question)
        except (BudgetExceeded, RunCancelled):
            raise
        except Exception:
            return []

    def _query_terms(self, question: str) -> set[str]:
        normalized = question.lower()
        for word in QUESTION_WORDS:
            normalized = normalized.replace(word, " ")

        terms = set()
        for part in re.findall(r"[a-z0-9]+|[一-鿿]+", normalized):
            if len(part) < 2:
                continue
            terms.add(part)
            max_size = min(8, len(part))
            for size in range(2, max_size + 1):
                for index in range(0, len(part) - size + 1):
                    terms.add(part[index : index + size])
        return terms

    def _keyword_score(self, query_terms: set[str], chunk: dict) -> float:
        if not query_terms:
            return 0.0

        searchable_text = self._searchable_text(chunk)
        matched_terms = {term for term in query_terms if term in searchable_text}
        if not matched_terms:
            return 0.0

        coverage = len(matched_terms) / len(query_terms)
        long_match_bonus = min(max((len(term) for term in matched_terms), default=0) / 10, 0.3)
        return min(coverage + long_match_bonus, 1.0)

    def _searchable_text(self, chunk: dict) -> str:
        columns = " ".join(str(column) for column in chunk.get("columns", []))
        return "\n".join(
            [
                str(chunk.get("title", "")),
                str(chunk.get("sheet_name", "")),
                columns,
                str(chunk.get("content", "")),
            ]
        ).lower()


retrieval_service = RetrievalService()
