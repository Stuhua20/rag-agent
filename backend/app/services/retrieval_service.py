from app.core.config import settings
from app.services.embedding_service import embedding_service
from app.services.json_store_service import json_store
from app.utils.similarity import cosine_similarity


class RetrievalService:
    def search(self, question: str, top_k: int | None = None, filters: dict | None = None) -> list[dict]:
        query_vector = embedding_service.embed_text(question)
        filters = filters or {}
        limit = top_k or settings.default_top_k
        threshold = self._score_threshold()
        chunks_by_id = {chunk["id"]: chunk for chunk in json_store.list_items("chunks.json")}
        scored_sources = []

        for embedding in json_store.list_items("embeddings.json"):
            metadata = embedding.get("metadata", {})
            if not self._matches_filters(metadata, filters):
                continue

            chunk = chunks_by_id.get(embedding.get("chunk_id"))
            if not chunk:
                continue

            score = cosine_similarity(query_vector, embedding.get("vector", []))
            if score < threshold:
                continue

            scored_sources.append(
                {
                    "chunk_id": chunk["id"],
                    "document_id": chunk["document_id"],
                    "sheet_id": chunk["sheet_id"],
                    "file_name": metadata.get("file_name", ""),
                    "sheet_name": chunk.get("sheet_name", metadata.get("sheet_name", "")),
                    "row_start": chunk.get("row_start"),
                    "row_end": chunk.get("row_end"),
                    "score": round(score, 6),
                    "content": chunk.get("content", ""),
                }
            )

        scored_sources.sort(key=lambda item: item["score"], reverse=True)
        return scored_sources[:limit]

    def _matches_filters(self, metadata: dict, filters: dict) -> bool:
        permission_level = filters.get("permission_level")
        if permission_level is not None and metadata.get("permission_level", 1) > permission_level:
            return False

        for key in ("department", "doc_type", "sheet_name"):
            value = filters.get(key)
            if value and metadata.get(key) != value:
                return False
        return True

    def _score_threshold(self) -> float:
        settings_json = json_store.read_json("settings.json")
        retrieval = settings_json.get("retrieval", {}) if isinstance(settings_json, dict) else {}
        return float(retrieval.get("score_threshold", settings.default_score_threshold))


retrieval_service = RetrievalService()
