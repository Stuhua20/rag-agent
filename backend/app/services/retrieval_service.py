import re
from collections import defaultdict

from app.core.config import settings
from app.services.embedding_service import embedding_service
from app.services.json_store_service import json_store
from app.utils.similarity import cosine_similarity


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
        indexed_document_ids = {
            document.get("id")
            for document in json_store.list_items("documents.json")
            if document.get("status") == "indexed"
        }
        chunks_by_id = {chunk["id"]: chunk for chunk in json_store.list_items("chunks.json")}
        scored_sources = []

        for embedding in json_store.list_items("embeddings.json"):
            if embedding.get("document_id") not in indexed_document_ids:
                continue
            chunk = chunks_by_id.get(embedding.get("chunk_id"))
            if not chunk:
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

    def search_multiple(
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
            return self.search(
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
            sources = self.search(
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

    def sources_for_chunk_ids(self, chunk_ids: list[str], limit: int | None = None) -> list[dict]:
        """返回确定性分析命中的 chunk，供回答引用。"""
        indexed_document_ids = {
            document.get("id")
            for document in json_store.list_items("documents.json")
            if document.get("status") == "indexed"
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
        permission_level = filters.get("permission_level")
        if permission_level is not None:
            try:
                if int(metadata.get("permission_level", 1)) > int(permission_level):
                    return False
            except (TypeError, ValueError):
                return False

        for key in ("sheet_name",):
            value = filters.get(key)
            if value and metadata.get(key) != value:
                return False
        return True

    def _safe_embed_text(self, question: str) -> list[float]:
        try:
            return embedding_service.embed_text(question)
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
